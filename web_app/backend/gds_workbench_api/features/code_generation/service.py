"""Execute one already-running SQL-only Code Generation Workflow Run."""

from __future__ import annotations

import json
import logging
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import Protocol, cast
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    GeneratedCodeSourceSystemRecord,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_etl_workbench.tools.change_sets.common import MAX_MODEL_STAGE_PAYLOAD_BYTES
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from pydantic import JsonValue

from gds_workbench_api.capabilities import CODE_GENERATION_AGENT_EXECUTION_MODE
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
    AgentRunPlan,
    ModelWorkflow,
    PostgresAgentRunPlanRepository,
)
from gds_workbench_api.features.workflows.authoring.progress import (
    AgentWorkflowProgress,
    intermediate_progress_points,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
    AgentExecutor,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner

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


class CodeGenerationExecutionDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class CodeGenerationPlanRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan: ...


class CodeGenerationContextRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> CodeGenerationExecutionContext: ...


class CodeGenerationChangeSetHandoff(Protocol):
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


class CodeGenerationNoOpCompleter(Protocol):
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


class CodeGenerationLifecycle(Protocol):
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


class CodeGenerationRunLifecycle(Protocol):
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


class CodeGenerationExecutor(Protocol):
    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> CodeGenerationExecutionResult: ...


class CodeGenerationWorkflow:
    """Bind the generic lifecycle to the fixed Code Generation execution path."""

    def __init__(
        self,
        *,
        lifecycle: CodeGenerationRunLifecycle,
        executor: CodeGenerationExecutor,
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
    ) -> object:
        return await self._executor.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=expected_model_revision,
            workflow_run_claim_token=workflow_run_claim_token,
        )


class DatabaseCodeGenerationExecutor:
    """Load frozen inputs, execute once through the selected adapter, then commit."""

    def __init__(
        self,
        *,
        database: CodeGenerationExecutionDatabase,
        authorizer: AuthorizationService,
        agent_executor: AgentExecutor,
        handoff: CodeGenerationChangeSetHandoff,
        no_op: CodeGenerationNoOpCompleter,
        lifecycle: CodeGenerationLifecycle,
        plan_repository: CodeGenerationPlanRepository | None = None,
        context_repository: CodeGenerationContextRepository | None = None,
        context_policy: AgentContextPolicy | None = None,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._plan_repository = plan_repository or PostgresAgentRunPlanRepository()
        self._context_repository = context_repository or PostgresCodeGenerationContextRepository()
        self._stage_runner = AgentStageRunner(
            executor=agent_executor,
            policy=context_policy or load_default_agent_context_policy(),
        )
        self._handoff = handoff
        self._no_op = no_op
        self._lifecycle = lifecycle

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
                message=f"SQL generation started for {target_count} target Objects.",
                current=0,
                total=target_count,
                finding_count=0,
            )

            guide_content = _guide_content(context)
            stage_plan = plan.model_copy(
                update={
                    "workflow_execution_mode": CODE_GENERATION_AGENT_EXECUTION_MODE,
                }
            )
            artifacts: list[GeneratedSqlArtifact] = []
            progress_points = intermediate_progress_points(target_count) | {target_count}
            highest_attempt = 1
            warning_seen = False
            for position, target in enumerate(context.targets, start=1):
                target_context = _target_agent_context(
                    context,
                    target_ref=target.target_ref,
                )
                validator = CodeGenerationCandidateValidator(
                    targets=(
                        CodeGenerationTargetReference(
                            target_ref=target.target_ref,
                            object_id=target.object_id,
                            source_system_codes=target.source_system_codes,
                        ),
                    )
                )
                outcome = await self._stage_runner.run(
                    plan=stage_plan,
                    stage_code="sql_generation",
                    resolver_values={
                        "workflow.code_generation.common.sql_generation.context": (
                            _target_context_manifest(target_context)
                        ),
                        "workflow.code_generation.sql_generation_guide": guide_content,
                        "workflow.validation_failures": [],
                    },
                    context=target_context,
                    output_schema=validator.output_schema(),
                    allowed_tool_names=(),
                    validator=validator,
                    max_candidate_bytes=MAX_MODEL_STAGE_PAYLOAD_BYTES,
                )
                artifacts.extend(validator.parse_validated(outcome.candidate))
                highest_attempt = max(highest_attempt, outcome.attempt_count)
                warning_seen = warning_seen or bool(outcome.was_repaired or outcome.warning_codes)
                if position in progress_points:
                    message = (
                        f"SQL generation validated {position} of {target_count} target Objects."
                    )
                    if warning_seen:
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
                            message="Code Generation completed with no effective change.",
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
                    message="Generated Code is ready in a validated draft.",
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
            artifact.object_id != by_ref[artifact.target_ref].object_id for artifact in artifacts
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
                modeled_entity_name=context.modeled_entity_name,
                artifact_name=artifact.artifact_name,
                artifact_type="sql_file",
                generated_code_content=artifact.generated_sql,
                generated_code_status="active",
            ),
        )
        system_records.extend(
            GeneratedCodeSourceSystemRecord(
                modeled_entity_type=modeled_entity_type,
                modeled_entity_name=context.modeled_entity_name,
                artifact_name=artifact.artifact_name,
                source_system_code=system_code,
                generated_code_source_system_status="active",
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
        current_names = {name.strip().casefold() for name in context.current_artifact_names}
        if record != prior_record or record.artifact_name.strip().casefold() not in current_names:
            changed.append(record)
    for key, (record, _) in applied.items():
        if key not in candidate_by_key and record.generated_code_status == "active":
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

    changed = [record for key, record in candidate_by_key.items() if record != applied.get(key)]
    changed.extend(
        record.model_copy(update={"generated_code_source_system_status": "inactive"})
        for key, record in applied.items()
        if key not in candidate_by_key and record.generated_code_source_system_status == "active"
    )
    return tuple(changed)


def _artifact_key(record: GeneratedCodeRecord) -> tuple[str, str, str]:
    return (
        record.modeled_entity_type,
        record.modeled_entity_name.strip().casefold(),
        record.artifact_name.strip().casefold(),
    )


def _source_system_key(
    record: GeneratedCodeSourceSystemRecord,
) -> tuple[str, str, str, str]:
    return (
        record.modeled_entity_type,
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
            "target_context_delivery": "request_context_original_context",
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
