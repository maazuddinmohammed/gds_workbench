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
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from pydantic import JsonValue

from gds_workbench_api.capabilities import CODE_GENERATION_AGENT_EXECUTION_MODE
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowRunStart,
    AgentWorkflowTerminalResult,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    ModelWorkflow,
    PostgresAgentRunPlanRepository,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
    AgentExecutor,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner

from .candidate import (
    CodeGenerationCandidateValidator,
    CodeGenerationTargetReference,
    GeneratedSqlArtifact,
)
from .context import (
    CodeGenerationExecutionContext,
    PostgresCodeGenerationContextRepository,
)
from .storage import (
    CodeGenerationArtifactContext,
    GeneratedSqlStorageResult,
    ModeledEntityType,
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


class GeneratedSqlStorage(Protocol):
    async def store(
        self,
        principal: RequestPrincipal,
        *,
        model_id: int,
        modeled_entity_type: ModeledEntityType,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        artifacts: tuple[GeneratedSqlArtifact, ...],
        contexts: tuple[CodeGenerationArtifactContext, ...],
    ) -> GeneratedSqlStorageResult: ...


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
    ) -> object: ...


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
        storage: GeneratedSqlStorage,
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
        self._storage = storage
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
    ) -> GeneratedSqlStorageResult:
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
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                event=AgentWorkflowEvent(
                    sequence=2,
                    attempt=1,
                    stage="code_generation.sql_generation",
                    status="running",
                    message="SQL generation started.",
                    current=0,
                    total=target_count,
                    finding_count=0,
                ),
            )

            guide_content = _guide_content(context)
            stage_plan = plan.model_copy(
                update={
                    "workflow_execution_mode": CODE_GENERATION_AGENT_EXECUTION_MODE,
                }
            )
            artifacts: list[GeneratedSqlArtifact] = []
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
                )
                artifacts.extend(validator.parse_validated(outcome.candidate))
                await self._lifecycle.append_event(
                    principal,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                    event=AgentWorkflowEvent(
                        sequence=position + 2,
                        attempt=outcome.attempt_count,
                        stage="code_generation.sql_generation",
                        status=(
                            "warning"
                            if outcome.was_repaired or outcome.warning_codes
                            else "running"
                        ),
                        message="SQL candidate passed complete backend validation.",
                        current=position,
                        total=target_count,
                        finding_count=position,
                    ),
                )
            return await self._storage.store(
                principal,
                model_id=model_id,
                modeled_entity_type=cast(ModeledEntityType, plan.modeled_entity_type),
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                artifacts=tuple(artifacts),
                contexts=context.targets,
            )
        except Exception as error:
            safe_error = _safe_execution_error(error)
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
                raise _safe_execution_error(persistence_error) from None
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


def _safe_execution_error(error: Exception) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    return CodeGenerationExecutionFailedError()
