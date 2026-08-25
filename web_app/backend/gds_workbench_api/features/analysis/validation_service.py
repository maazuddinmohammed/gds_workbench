"""Governed deterministic Analysis validation workflow execution."""

from __future__ import annotations

import asyncio
import logging
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from math import ceil
from typing import Any, Literal, LiteralString, Never, Protocol
from uuid import UUID

from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DatabricksConnectionConfigurationError,
    DependencyUnavailableError,
    InvalidRequestError,
    TenantLockedError,
    TenantLockRequiredError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_etl_workbench.tools.databricks.executor import DatabricksSqlConnection
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gds_workbench_api.features.models import ModelRevisionConflictError
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowRunStart,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    ModelWorkflow,
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.execution.fence import (
    assert_workflow_run_claim,
)
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError

from .validation_execution import (
    AnalysisValidationEvidence,
    AnalysisValidationPolicy,
    AnalysisValidationQuery,
    AnalysisValidationRelationship,
    ConnectorAnalysisValidationExecutor,
    build_analysis_validation_query,
    load_default_analysis_validation_policy,
)

_logger = logging.getLogger(__name__)

_RUN_BINDING_SQL: LiteralString = """
SELECT run.workflow_run_id,
       run.model_id,
       target_model.model_revision,
       run.requested_batch_id
  FROM application.workflow_run AS run
  JOIN model.model AS target_model
    ON target_model.model_id = run.model_id
   AND target_model.tenant_id = %s
   AND target_model.is_active
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
   AND run.model_workflow = 'analysis'
   AND run.workflow_execution_mode IS NULL
   AND run.workflow_run_state = 'running'
"""

_CONTEXT_SQL: LiteralString = """
SELECT context.*
  FROM application.get_analysis_validation_execution_context(
       %s, %s, %s, %s, %s, %s
  ) AS context
 ORDER BY context.analysis_result_id
"""

_CONNECTION_VALUES_SQL: LiteralString = """
SELECT connection_values.*
  FROM application.get_analysis_validation_connection_values(
       %s, %s, %s, %s, %s, %s
  ) AS connection_values
 ORDER BY connection_values.gds_connection_id
"""

_PERSIST_SQL: LiteralString = """
SELECT persisted.changed,
       persisted.workflow_run_id,
       persisted.model_id,
       persisted.model_revision,
       persisted.submitted_result_count,
       persisted.changed_result_count
  FROM application.persist_analysis_validation_results(
       %s, %s, %s, %s, %s, %s, %s
  ) AS persisted
"""

_COMPLETE_SQL: LiteralString = """
SELECT completed.changed,
       completed.workflow_run_id,
       completed.workflow_run_state,
       completed.completed_time
  FROM application.complete_workflow_run(
       %s, %s, %s, %s, %s, %s
  ) AS completed
"""


@dataclass(frozen=True, slots=True)
class AnalysisValidationExecutionTarget:
    relationship: AnalysisValidationRelationship
    connection: DatabricksSqlConnection = field(repr=False)


@dataclass(frozen=True, slots=True)
class AnalysisValidationExecutionContext:
    workflow_run_id: int
    model_id: int
    model_revision: int
    requested_batch_id: str | None
    targets: tuple[AnalysisValidationExecutionTarget, ...]


class AnalysisValidationCommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    changed: bool
    workflow_run_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    submitted_result_count: int = Field(ge=0)
    changed_result_count: int = Field(ge=0)
    workflow_run_state: Literal["completed", "completed_with_repair"]


class AnalysisValidationExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="analysis_validation_execution_failed",
            message=("Analysis validation failed before complete results were committed."),
        )


class AnalysisValidationDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...

    def write_transaction(
        self,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class AnalysisValidationLifecycle(Protocol):
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
    ) -> object: ...


class AnalysisValidationRepository(Protocol):
    async def load_context(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> AnalysisValidationExecutionContext: ...

    async def commit(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        validation_results: list[dict[str, object]],
    ) -> AnalysisValidationCommitResult: ...


class AnalysisValidationQueryExecutor(Protocol):
    async def execute(
        self,
        *,
        connection: DatabricksSqlConnection,
        query: AnalysisValidationQuery,
        timeout_seconds: int,
    ) -> AnalysisValidationEvidence: ...


class DatabaseAnalysisValidationRepository:
    """Resolve one immutable input snapshot and atomically commit its evidence."""

    def __init__(
        self,
        *,
        database: AnalysisValidationDatabase,
        environment_code: str,
    ) -> None:
        normalized_environment = environment_code.strip()
        if not normalized_environment or len(normalized_environment) > 100:
            raise ValueError("Analysis validation Environment code is invalid")
        self._database = database
        self._environment_code = normalized_environment

    async def load_context(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> AnalysisValidationExecutionContext:
        identity = _identity_triple(principal)
        try:
            async with self._database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                binding = await transaction.fetch_one(
                    _RUN_BINDING_SQL,
                    (tenant_id, model_id, workflow_run_id),
                )
                if binding is None:
                    raise WorkflowRunNotFoundError()
                model_revision = _positive_int(binding.get("model_revision"))
                if model_revision != expected_model_revision:
                    raise ModelRevisionConflictError()
                requested_batch_id = _optional_text(binding.get("requested_batch_id"))
                rows = await transaction.fetch_all(
                    _CONTEXT_SQL,
                    identity
                    + (
                        workflow_run_id,
                        expected_model_revision,
                        self._environment_code,
                    ),
                )
                if not rows:
                    return AnalysisValidationExecutionContext(
                        workflow_run_id=workflow_run_id,
                        model_id=model_id,
                        model_revision=model_revision,
                        requested_batch_id=requested_batch_id,
                        targets=(),
                    )
                relationships = tuple(
                    _relationship_from_row(
                        row,
                        workflow_run_id=workflow_run_id,
                        model_id=model_id,
                        model_revision=model_revision,
                        requested_batch_id=requested_batch_id,
                    )
                    for row in rows
                )
                connection_rows = await transaction.fetch_all(
                    _CONNECTION_VALUES_SQL,
                    identity
                    + (
                        workflow_run_id,
                        expected_model_revision,
                        self._environment_code,
                    ),
                )
                connections = _connection_map(
                    connection_rows,
                    workflow_run_id=workflow_run_id,
                    model_id=model_id,
                    model_revision=model_revision,
                    environment_code=self._environment_code,
                )
        except Exception as error:
            _raise_repository_error(error)

        expected_connection_ids = {relationship.gds_connection_id for relationship in relationships}
        if set(connections) != expected_connection_ids:
            raise DatabricksConnectionConfigurationError("missing")
        return AnalysisValidationExecutionContext(
            workflow_run_id=workflow_run_id,
            model_id=model_id,
            model_revision=model_revision,
            requested_batch_id=requested_batch_id,
            targets=tuple(
                AnalysisValidationExecutionTarget(
                    relationship=relationship,
                    connection=connections[relationship.gds_connection_id],
                )
                for relationship in relationships
            ),
        )

    async def commit(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        validation_results: list[dict[str, object]],
    ) -> AnalysisValidationCommitResult:
        identity = _identity_triple(principal)
        try:
            async with self._database.write_transaction() as transaction:
                await assert_workflow_run_claim(
                    transaction,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                persisted = await transaction.fetch_one(
                    _PERSIST_SQL,
                    identity
                    + (
                        workflow_run_id,
                        expected_model_revision,
                        self._environment_code,
                        Jsonb(validation_results),
                    ),
                )
                if persisted is None:
                    raise DependencyUnavailableError()
                model_revision = _positive_int(persisted.get("model_revision"))
                completed = await transaction.fetch_one(
                    _COMPLETE_SQL,
                    identity
                    + (
                        workflow_run_id,
                        model_revision,
                        len(validation_results),
                    ),
                )
                if completed is None:
                    raise DependencyUnavailableError()
                result_document = {
                    **persisted,
                    "workflow_run_state": completed.get("workflow_run_state"),
                }
        except Exception as error:
            _raise_repository_error(error)
        try:
            return AnalysisValidationCommitResult.model_validate(
                result_document,
                strict=True,
            )
        except ValidationError:
            raise DependencyUnavailableError() from None


class AnalysisValidationWorkflow:
    """Run fixed aggregate validation without agent, fallback, or partial writes."""

    def __init__(
        self,
        *,
        lifecycle: AnalysisValidationLifecycle,
        repository: AnalysisValidationRepository,
        executor: AnalysisValidationQueryExecutor | None = None,
        policy: AnalysisValidationPolicy | None = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._repository = repository
        self._executor = executor or ConnectorAnalysisValidationExecutor()
        self._policy = policy or load_default_analysis_validation_policy()

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
            expected_workflow="analysis",
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
    ) -> AnalysisValidationCommitResult | None:
        try:
            context = await self._repository.load_context(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
            )
            _validate_context_binding(
                context,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                max_relationships=self._policy.max_relationships,
            )
            await self._lifecycle.append_event(
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                event=AgentWorkflowEvent(
                    sequence=2,
                    attempt=1,
                    stage="analysis.relationship_validation",
                    status="running",
                    message=(
                        "No eligible Analysis relationships require validation."
                        if not context.targets
                        else "Analysis relationship validation started."
                    ),
                    current=0 if context.targets else None,
                    total=len(context.targets) if context.targets else None,
                    finding_count=0,
                ),
            )
            payload = await self._execute_all(
                principal,
                context=context,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            return await self._repository.commit(
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                validation_results=payload,
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
            except Exception:
                _logger.warning(
                    "Analysis validation failure state could not be persisted.",
                    extra={
                        "workflow_run_id": workflow_run_id,
                        "model_id": model_id,
                        "failure_code": safe_error.code[:100],
                    },
                )
                raise DependencyUnavailableError() from None
            return None

    async def _execute_all(
        self,
        principal: RequestPrincipal,
        *,
        context: AnalysisValidationExecutionContext,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> list[dict[str, object]]:
        if not context.targets:
            return []
        targets = tuple(
            sorted(
                context.targets,
                key=lambda target: target.relationship.analysis_result_id,
            )
        )
        queries = tuple(
            build_analysis_validation_query(
                target.relationship,
                requested_batch_id=context.requested_batch_id,
            )
            for target in targets
        )
        thresholds = _progress_thresholds(
            len(targets),
            self._policy.max_progress_events - 1,
        )
        threshold_index = 0
        sequence = 3
        evidence_by_id: dict[int, AnalysisValidationEvidence] = {}
        chunk_size = self._policy.max_parallel_queries
        for start in range(0, len(targets), chunk_size):
            target_chunk = targets[start : start + chunk_size]
            query_chunk = queries[start : start + chunk_size]
            evidence_chunk = await asyncio.gather(
                *(
                    self._executor.execute(
                        connection=target.connection,
                        query=query,
                        timeout_seconds=self._policy.statement_timeout_seconds,
                    )
                    for target, query in zip(
                        target_chunk,
                        query_chunk,
                        strict=True,
                    )
                )
            )
            for target, evidence in zip(
                target_chunk,
                evidence_chunk,
                strict=True,
            ):
                evidence_by_id[target.relationship.analysis_result_id] = evidence
            completed = min(start + len(target_chunk), len(targets))
            if threshold_index < len(thresholds) and completed >= thresholds[threshold_index]:
                while (
                    threshold_index < len(thresholds) and completed >= thresholds[threshold_index]
                ):
                    threshold_index += 1
                await self._lifecycle.append_event(
                    principal,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                    event=AgentWorkflowEvent(
                        sequence=sequence,
                        attempt=1,
                        stage="analysis.relationship_validation",
                        status="running",
                        message=(
                            "Analysis relationship validation completed."
                            if completed == len(targets)
                            else "Analysis relationship validation is running."
                        ),
                        current=completed,
                        total=len(targets),
                        finding_count=completed,
                    ),
                )
                sequence += 1

        policy_digest = self._policy.validation_policy_digest
        return [
            {
                "analysis_result_id": target.relationship.analysis_result_id,
                "source_context_digest": target.relationship.source_context_digest,
                "validation_policy_version": self._policy.validation_policy_version,
                "validation_policy_digest": policy_digest,
                **evidence_by_id[target.relationship.analysis_result_id].model_dump(mode="python"),
            }
            for target in targets
        ]


def _relationship_from_row(
    row: dict[str, Any],
    *,
    workflow_run_id: int,
    model_id: int,
    model_revision: int,
    requested_batch_id: str | None,
) -> AnalysisValidationRelationship:
    if (
        _positive_int(row.get("workflow_run_id")) != workflow_run_id
        or _positive_int(row.get("model_id")) != model_id
        or _positive_int(row.get("model_revision")) != model_revision
        or _optional_text(row.get("requested_batch_id")) != requested_batch_id
    ):
        raise DependencyUnavailableError()
    source_context_digest = _required_text(row.get("source_context_digest"))
    document = {
        "analysis_result_id": row.get("analysis_result_id"),
        "relationship_kind": row.get("relationship_kind"),
        "relationship_confidence": row.get("relationship_confidence"),
        "relationship_basis": row.get("relationship_basis"),
        "analysis_result_status": row.get("analysis_result_status"),
        "analysis_result_is_locked": row.get("analysis_result_is_locked"),
        "gds_connection_id": row.get("gds_connection_id"),
        "source_context_digest": source_context_digest,
        "from_endpoint": {
            "relation_catalog": row.get("from_relation_catalog"),
            "relation_schema": row.get("from_relation_schema"),
            "relation_object": row.get("from_relation_object"),
            "object_id": row.get("from_object_id"),
            "attribute_id": row.get("from_attribute_id"),
            "attribute_name": row.get("from_attribute_name"),
            "attribute_data_type": row.get("from_attribute_data_type"),
            "batch_attribute_name": row.get("from_batch_attribute_name"),
            "batch_attribute_data_type": row.get("from_batch_attribute_data_type"),
        },
        "to_endpoint": {
            "relation_catalog": row.get("to_relation_catalog"),
            "relation_schema": row.get("to_relation_schema"),
            "relation_object": row.get("to_relation_object"),
            "object_id": row.get("to_object_id"),
            "attribute_id": row.get("to_attribute_id"),
            "attribute_name": row.get("to_attribute_name"),
            "attribute_data_type": row.get("to_attribute_data_type"),
            "batch_attribute_name": row.get("to_batch_attribute_name"),
            "batch_attribute_data_type": row.get("to_batch_attribute_data_type"),
        },
    }
    try:
        return AnalysisValidationRelationship.model_validate(document, strict=True)
    except ValidationError:
        raise DependencyUnavailableError() from None


def _connection_map(
    rows: list[dict[str, Any]],
    *,
    workflow_run_id: int,
    model_id: int,
    model_revision: int,
    environment_code: str,
) -> dict[int, DatabricksSqlConnection]:
    connections: dict[int, DatabricksSqlConnection] = {}
    for row in rows:
        failure_code = _optional_text(row.get("failure_code"))
        if failure_code is not None:
            reason = "environment" if "environment" in failure_code else "missing"
            raise DatabricksConnectionConfigurationError(reason)
        if (
            _positive_int(row.get("workflow_run_id")) != workflow_run_id
            or _positive_int(row.get("model_id")) != model_id
            or _positive_int(row.get("model_revision")) != model_revision
            or _required_text(row.get("environment_code")) != environment_code
        ):
            raise DependencyUnavailableError()
        connection_id = _positive_int(row.get("gds_connection_id"))
        if connection_id in connections:
            raise DependencyUnavailableError()
        connections[connection_id] = DatabricksSqlConnection(
            server_hostname=_required_text(row.get("databricks_host_name")),
            http_path=_required_text(row.get("databricks_http_path")),
            access_token=_required_text(row.get("databricks_token")),
        )
    return connections


def _validate_context_binding(
    context: AnalysisValidationExecutionContext,
    *,
    model_id: int,
    workflow_run_id: int,
    expected_model_revision: int,
    max_relationships: int,
) -> None:
    result_ids = [target.relationship.analysis_result_id for target in context.targets]
    if (
        context.workflow_run_id != workflow_run_id
        or context.model_id != model_id
        or context.model_revision != expected_model_revision
        or len(context.targets) > max_relationships
        or len(result_ids) != len(set(result_ids))
        or any(target.relationship.source_context_digest is None for target in context.targets)
    ):
        raise InvalidRequestError("The Analysis validation run context is no longer valid.")


def _progress_thresholds(total: int, budget: int) -> tuple[int, ...]:
    if total < 1 or budget < 1:
        return ()
    return tuple(sorted({ceil(total * step / budget) for step in range(1, budget + 1)}))


def _identity_triple(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    principal_type = "service_principal" if principal.actor_kind is ActorKind.WORKLOAD else "user"
    return principal.entra_tenant_id, principal.entra_object_id, principal_type


def _positive_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DependencyUnavailableError()
    return value


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DependencyUnavailableError()
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _required_text(value)


def _safe_execution_error(error: Exception) -> WorkbenchError:
    if isinstance(error, WorkbenchError):
        return error
    return AnalysisValidationExecutionFailedError()


def _raise_repository_error(error: Exception) -> Never:
    if isinstance(error, WorkbenchError) and not isinstance(
        error,
        DependencyUnavailableError,
    ):
        raise error
    message = _primary_database_message(error)
    if message == "stale_model_revision":
        raise ModelRevisionConflictError() from error
    if "analysis_validation_run_not_found" in message:
        raise WorkflowRunNotFoundError() from error
    if "workflow_run_owner_mismatch" in message:
        raise AuthorizationDeniedError() from error
    if "tenant_lock_required" in message:
        raise TenantLockRequiredError() from error
    if "tenant_locked" in message:
        raise TenantLockedError("another Principal") from error
    if "analysis_validation_environment_not_found" in message:
        raise DatabricksConnectionConfigurationError("environment") from error
    if message.startswith("analysis_validation_") or message.startswith("invalid_request:"):
        raise InvalidRequestError(
            "The Analysis validation run context is no longer valid."
        ) from error
    raise DependencyUnavailableError() from error


def _primary_database_message(error: Exception) -> str:
    current: BaseException = error
    for _ in range(4):
        diagnostic = getattr(current, "diag", None)
        primary = getattr(diagnostic, "message_primary", None)
        if isinstance(primary, str) and primary:
            return primary
        cause = current.__cause__
        if cause is None:
            return str(current)
        current = cause
    return ""


__all__ = [
    "AnalysisValidationCommitResult",
    "AnalysisValidationExecutionContext",
    "AnalysisValidationExecutionFailedError",
    "AnalysisValidationExecutionTarget",
    "AnalysisValidationWorkflow",
    "DatabaseAnalysisValidationRepository",
]
