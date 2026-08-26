"""Governed orchestration for deterministic bulk Profiling runs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Never, Protocol
from uuid import UUID

from fastapi import APIRouter, Path, Request, Response, status
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DatabricksConnectionConfigurationError,
    DatabricksConnectionFailedError,
    DatabricksResultTooLargeError,
    DatabricksStatementFailedError,
    DependencyUnavailableError,
    InvalidRequestError,
    TenantLockedError,
    TenantLockRequiredError,
    TenantWorkflowConflictError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_etl_workbench.tools.databricks.executor import DatabricksSqlConnection
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.features.models import ModelRevisionConflictError
from gds_workbench_api.features.profiling.execution import (
    ProfileAttribute,
    ProfileMetric,
    ProfileObject,
    ProfilingExecutor,
    ProfilingPolicy,
    build_profile_queries,
    load_default_profiling_policy,
)
from gds_workbench_api.features.workflows.execution.fence import (
    assert_workflow_run_claim,
)
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError

_logger = logging.getLogger(__name__)

_RUN_BINDING_SQL = """
SELECT target_model.model_revision,
       run.model_workflow
  FROM application.workflow_run AS run
  JOIN model.model AS target_model
    ON target_model.model_id = run.model_id
   AND target_model.is_active
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND run.workflow_run_id = %s
"""

_START_SQL = """
SELECT started.changed,
       started.workflow_run_id,
       started.workflow_run_state,
       started.started_time
  FROM application.start_workflow_run(%s, %s, %s, %s, %s) AS started
"""

_CONTEXT_SQL = """
SELECT *
  FROM application.get_profiling_execution_context(%s, %s, %s, %s, %s)
"""

_CONNECTION_VALUES_SQL = """
SELECT *
  FROM application.get_profiling_connection_values(%s, %s, %s, %s, %s, %s)
"""

_APPEND_EVENT_SQL = """
SELECT event.model_event_log_id
  FROM application.append_workflow_run_event(
       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
  ) AS event
"""

_PERSIST_SQL = """
SELECT persisted.changed,
       persisted.workflow_run_id,
       persisted.model_id,
       persisted.model_revision,
       persisted.submitted_profile_count,
       persisted.changed_profile_count
  FROM application.persist_profiling_results(
       %s, %s, %s, %s, %s, %s
  ) AS persisted
"""

_COMPLETE_SQL = """
SELECT completed.changed,
       completed.workflow_run_id,
       completed.workflow_run_state,
       completed.completed_time
  FROM application.complete_workflow_run(%s, %s, %s, %s, %s, %s) AS completed
"""

_FAIL_SQL = """
SELECT failed.changed,
       failed.workflow_run_id,
       failed.workflow_run_state,
       failed.completed_time
  FROM application.fail_workflow_run(%s, %s, %s, %s, %s, %s, %s) AS failed
"""


class ProfilingRunStart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    changed: bool
    workflow_run_id: int = Field(gt=0)
    workflow_run_state: Literal[
        "queued",
        "running",
        "completed",
        "completed_with_repair",
        "failed",
    ]
    model_revision: int = Field(gt=0)


class ExecuteProfilingRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)


class ProfilingCommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    changed: bool
    workflow_run_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    submitted_profile_count: int = Field(ge=0, le=50_000)
    changed_profile_count: int = Field(ge=0, le=50_000)
    workflow_run_state: Literal["completed"]


@dataclass(frozen=True, slots=True)
class ProfilingExecutionTarget:
    object: ProfileObject
    connection: DatabricksSqlConnection = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProfilingExecutionContext:
    workflow_run_id: int
    model_id: int
    model_revision: int
    requested_batch_id: str | None
    targets: tuple[ProfilingExecutionTarget, ...]

    def __post_init__(self) -> None:
        if self.workflow_run_id < 1 or self.model_id < 1 or self.model_revision < 1:
            raise ValueError("Profiling execution identifiers must be positive")
        if not 1 <= len(self.targets) <= 50_000:
            raise ValueError("Profiling execution targets are incomplete")
        object_ids = tuple(target.object.object_id for target in self.targets)
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("Profiling execution Object IDs must be unique")
        if self.requested_batch_id is not None and (
            not self.requested_batch_id.strip()
            or len(self.requested_batch_id.encode("utf-8")) > 500
        ):
            raise ValueError("Profiling Batch ID must be bounded and nonblank")


class ProfilingWorkflowRepository(Protocol):
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingRunStart: ...

    async def load_context(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingExecutionContext: ...

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        sequence: int,
        stage: str,
        status: str,
        message: str,
        current: int | None,
        total: int | None,
        finding_count: int,
    ) -> None: ...

    async def commit(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        profiles: list[dict[str, object]],
    ) -> ProfilingCommitResult: ...

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        failure_code: str,
        safe_failure_message: str,
    ) -> None: ...


class ProfilingWorkflowDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...

    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseProfilingWorkflowRepository:
    """Use only fixed governed functions for run state, secrets, and writes."""

    def __init__(
        self,
        *,
        database: ProfilingWorkflowDatabase,
        environment_code: str,
    ) -> None:
        if not environment_code.strip() or len(environment_code) > 100:
            raise ValueError("Profiling Environment code is invalid")
        self._database = database
        self._environment_code = environment_code

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingRunStart:
        identity = _identity_triple(principal)
        try:
            async with self._database.write_transaction() as transaction:
                await _require_profiling_binding(
                    transaction,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                )
                row = await transaction.fetch_one(
                    _START_SQL,
                    identity + (workflow_run_id, expected_model_revision),
                )
        except Exception as error:
            _raise_repository_error(error)
        if row is None:
            raise DependencyUnavailableError()
        return ProfilingRunStart.model_validate(
            {
                "changed": row.get("changed"),
                "workflow_run_id": row.get("workflow_run_id"),
                "workflow_run_state": row.get("workflow_run_state"),
                "model_revision": expected_model_revision,
            },
            strict=False,
        )

    async def load_context(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingExecutionContext:
        identity = _identity_triple(principal)
        try:
            async with self._database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await _require_profiling_binding(
                    transaction,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                )
                context_rows = await transaction.fetch_all(
                    _CONTEXT_SQL,
                    identity + (workflow_run_id, expected_model_revision),
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
        except Exception as error:
            _raise_repository_error(error)
        if not context_rows or not connection_rows:
            raise DependencyUnavailableError()

        credentials: dict[int, DatabricksSqlConnection] = {}
        for row in connection_rows:
            failure_code = row.get("failure_code")
            if isinstance(failure_code, str):
                _raise_connection_configuration_error(failure_code)
            connection_id = _required_int(row, "gds_connection_id")
            credentials[connection_id] = DatabricksSqlConnection(
                server_hostname=_required_text(row, "databricks_host_name"),
                http_path=_required_text(row, "databricks_http_path"),
                access_token=_required_text(row, "databricks_token"),
            )

        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in context_rows:
            if (
                _required_int(row, "workflow_run_id") != workflow_run_id
                or _required_int(row, "model_id") != model_id
                or _required_int(row, "model_revision") != expected_model_revision
            ):
                raise DependencyUnavailableError()
            grouped.setdefault(_required_int(row, "object_id"), []).append(row)

        targets: list[tuple[int, ProfilingExecutionTarget]] = []
        used_connection_ids: set[int] = set()
        for object_rows in grouped.values():
            object_rows.sort(
                key=lambda row: (
                    _required_int(row, "attribute_ordinal_position"),
                    _required_int(row, "attribute_id"),
                )
            )
            header = object_rows[0]
            connection_id = _required_int(header, "gds_connection_id")
            connection = credentials.get(connection_id)
            if connection is None:
                raise DependencyUnavailableError()
            used_connection_ids.add(connection_id)
            target_object = ProfileObject(
                object_id=_required_int(header, "object_id"),
                connection_id=connection_id,
                catalog=_required_text(header, "relation_catalog"),
                schema=_required_text(header, "relation_schema"),
                table=_required_text(header, "relation_object"),
                batch_attribute_name=_optional_text(
                    header,
                    "batch_attribute_name",
                ),
                attributes=tuple(
                    ProfileAttribute(
                        attribute_id=_required_int(row, "attribute_id"),
                        name=_required_text(row, "attribute_name"),
                        data_type=_required_text(row, "attribute_data_type"),
                    )
                    for row in object_rows
                ),
            )
            targets.append(
                (
                    _required_int(header, "selection_order"),
                    ProfilingExecutionTarget(
                        object=target_object,
                        connection=connection,
                    ),
                )
            )
        if used_connection_ids != set(credentials):
            raise DependencyUnavailableError()
        targets.sort(key=lambda item: item[0])
        first = context_rows[0]
        return ProfilingExecutionContext(
            workflow_run_id=workflow_run_id,
            model_id=model_id,
            model_revision=expected_model_revision,
            requested_batch_id=_optional_text(first, "requested_batch_id"),
            targets=tuple(target for _order, target in targets),
        )

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        sequence: int,
        stage: str,
        status: str,
        message: str,
        current: int | None,
        total: int | None,
        finding_count: int,
    ) -> None:
        identity = _identity_triple(principal)
        try:
            async with self._database.write_transaction() as transaction:
                await assert_workflow_run_claim(
                    transaction,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                row = await transaction.fetch_one(
                    _APPEND_EVENT_SQL,
                    identity
                    + (
                        workflow_run_id,
                        expected_model_revision,
                        sequence,
                        1,
                        stage,
                        status,
                        message,
                        current,
                        total,
                        finding_count,
                    ),
                )
        except Exception as error:
            _raise_repository_error(error)
        if row is None:
            raise DependencyUnavailableError()

    async def commit(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        profiles: list[dict[str, object]],
    ) -> ProfilingCommitResult:
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
                        Jsonb(profiles),
                    ),
                )
                if persisted is None:
                    raise DependencyUnavailableError()
                completed = await transaction.fetch_one(
                    _COMPLETE_SQL,
                    identity
                    + (
                        workflow_run_id,
                        _required_int(persisted, "model_revision"),
                        _required_int(persisted, "submitted_profile_count"),
                    ),
                )
                if completed is None:
                    raise DependencyUnavailableError()
        except Exception as error:
            _raise_repository_error(error)
        return ProfilingCommitResult.model_validate(
            {
                **persisted,
                "workflow_run_state": completed["workflow_run_state"],
            },
            strict=False,
        )

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        failure_code: str,
        safe_failure_message: str,
    ) -> None:
        identity = _identity_triple(principal)
        try:
            async with self._database.write_transaction() as transaction:
                await assert_workflow_run_claim(
                    transaction,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                row = await transaction.fetch_one(
                    _FAIL_SQL,
                    identity
                    + (
                        workflow_run_id,
                        expected_model_revision,
                        failure_code,
                        safe_failure_message,
                    ),
                )
        except Exception as error:
            _raise_repository_error(error)
        if row is None:
            raise DependencyUnavailableError()


class ProfilingWorkflowService(Protocol):
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingRunStart: ...

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> None: ...


class ProfilingWorkflowOrchestrator:
    """Plan, execute, validate, and atomically commit one started run."""

    def __init__(
        self,
        *,
        repository: ProfilingWorkflowRepository,
        executor: ProfilingExecutor,
        policy: ProfilingPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._executor = executor
        self._policy = policy or load_default_profiling_policy()

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingRunStart:
        return await self._repository.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
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
    ) -> None:
        try:
            context = await self._repository.load_context(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
            )
            if (
                context.workflow_run_id != workflow_run_id
                or context.model_id != model_id
                or context.model_revision != expected_model_revision
            ):
                raise RuntimeError("Profiling execution context does not match the run")

            plans = tuple(
                (target, query)
                for target in context.targets
                for query in build_profile_queries(
                    target.object,
                    requested_batch_id=context.requested_batch_id,
                    attributes_per_query=self._policy.attributes_per_query,
                )
            )
            await self._repository.append_event(
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                sequence=2,
                stage="profiling.prepare",
                status="running",
                message="Profiling queries prepared.",
                current=0,
                total=len(plans),
                finding_count=0,
            )

            completed = 0
            metrics_by_attribute: dict[int, tuple[int, ProfileMetric]] = {}
            for offset in range(0, len(plans), self._policy.max_parallel_queries):
                batch = plans[offset : offset + self._policy.max_parallel_queries]
                results = await asyncio.gather(
                    *(
                        self._executor.execute(
                            connection=target.connection,
                            query=query,
                            timeout_seconds=self._policy.statement_timeout_seconds,
                        )
                        for target, query in batch
                    )
                )
                for (target, query), metrics in zip(batch, results, strict=True):
                    if tuple(metric.attribute_id for metric in metrics) != query.attribute_ids:
                        raise RuntimeError("Profiling result coverage is invalid")
                    for metric in metrics:
                        if metric.attribute_id in metrics_by_attribute:
                            raise RuntimeError("Profiling result coverage is duplicated")
                        metrics_by_attribute[metric.attribute_id] = (
                            target.object.object_id,
                            metric,
                        )
                    completed += 1
                    await self._repository.append_event(
                        principal,
                        workflow_run_id=workflow_run_id,
                        expected_model_revision=expected_model_revision,
                        workflow_run_claim_token=workflow_run_claim_token,
                        sequence=2 + completed,
                        stage="profiling.execute",
                        status="running",
                        message="A bounded Profiling query completed.",
                        current=completed,
                        total=len(plans),
                        finding_count=len(metrics_by_attribute),
                    )

            attributes = {
                attribute.attribute_id: (target.object, attribute)
                for target in context.targets
                for attribute in target.object.attributes
            }
            if set(metrics_by_attribute) != set(attributes):
                raise RuntimeError("Profiling result coverage is incomplete")
            profiles: list[dict[str, object]] = []
            for attribute_id in sorted(attributes):
                target_object, attribute = attributes[attribute_id]
                object_id, metric = metrics_by_attribute[attribute_id]
                if object_id != target_object.object_id:
                    raise RuntimeError("Profiling result Object membership is invalid")
                profile = metric.model_dump(mode="python")
                profile["object_id"] = object_id
                profile["source_context_digest"] = _source_context_digest(
                    target_object,
                    attribute_id=attribute_id,
                    attribute_name=attribute.name,
                    attribute_data_type=attribute.data_type,
                    requested_batch_id=context.requested_batch_id,
                )
                profiles.append(profile)

            await self._repository.commit(
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                profiles=profiles,
            )
        except Exception as error:
            failure_code, safe_message = _safe_failure(error)
            try:
                await self._repository.fail(
                    principal,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                    failure_code=failure_code,
                    safe_failure_message=safe_message,
                )
            except Exception:
                _logger.warning(
                    "Profiling failure state could not be persisted.",
                    extra={
                        "workflow_run_id": workflow_run_id,
                        "model_id": model_id,
                        "failure_code": failure_code,
                    },
                )
                raise DependencyUnavailableError() from None


def _source_context_digest(
    target: ProfileObject,
    *,
    attribute_id: int,
    attribute_name: str,
    attribute_data_type: str,
    requested_batch_id: str | None,
) -> str:
    encoded = json.dumps(
        {
            "attribute_data_type": attribute_data_type,
            "attribute_id": attribute_id,
            "attribute_name": attribute_name,
            "batch_attribute_name": target.batch_attribute_name,
            "catalog": target.catalog,
            "object_id": target.object_id,
            "requested_batch_id": requested_batch_id,
            "schema": target.schema_name,
            "table": target.table,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_failure(error: Exception) -> tuple[str, str]:
    if isinstance(error, DatabricksConnectionFailedError):
        return (
            "databricks_connection_failed",
            "The Databricks SQL Warehouse connection failed.",
        )
    if isinstance(error, DatabricksStatementFailedError):
        return (
            "databricks_statement_failed",
            "Databricks rejected a Profiling query. Check registered metadata "
            "and Warehouse permissions.",
        )
    if isinstance(error, DatabricksResultTooLargeError):
        return (
            "databricks_profile_result_invalid",
            "Databricks returned an invalid or incomplete Profiling aggregate result.",
        )
    if isinstance(error, WorkbenchError):
        return error.code[:100], error.message[:2000]
    return (
        "profiling_execution_failed",
        "Profiling failed before results could be committed.",
    )


async def _require_profiling_binding(
    transaction: ReadTransaction | WriteTransaction,
    *,
    tenant_id: int,
    model_id: int,
    workflow_run_id: int,
) -> None:
    row = await transaction.fetch_one(
        _RUN_BINDING_SQL,
        (tenant_id, model_id, workflow_run_id),
    )
    if row is None:
        raise WorkflowRunNotFoundError()
    if row.get("model_workflow") != "profiling":
        raise InvalidRequestError("The requested Workflow Run is not a Profiling run.")


def _identity_triple(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    principal_type = "service_principal" if principal.actor_kind is ActorKind.WORKLOAD else "user"
    return principal.entra_tenant_id, principal.entra_object_id, principal_type


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DependencyUnavailableError()
    return value


def _required_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DependencyUnavailableError()
    return value


def _optional_text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DependencyUnavailableError()
    return value


def _raise_connection_configuration_error(code: str) -> Never:
    if code == "environment_not_found":
        raise DatabricksConnectionConfigurationError("environment")
    if code == "connection_values_missing":
        raise DatabricksConnectionConfigurationError("missing")
    raise DatabricksConnectionConfigurationError("invalid")


def _raise_repository_error(error: Exception) -> Never:
    if isinstance(error, WorkbenchError) and not isinstance(
        error,
        DependencyUnavailableError,
    ):
        raise error
    message = _primary_database_message(error)
    if message == "stale_model_revision":
        raise ModelRevisionConflictError() from error
    if message == "tenant_workflow_conflict":
        raise TenantWorkflowConflictError() from error
    if message.startswith("profiling_run_not_found:"):
        raise WorkflowRunNotFoundError() from error
    if message.startswith("workflow_run_owner_mismatch:"):
        raise AuthorizationDeniedError() from error
    if message.startswith("profiling_execution_denied:"):
        code = message.partition(":")[2].strip()
        if code == "tenant_lock_required":
            raise TenantLockRequiredError() from error
        if code == "tenant_locked":
            raise TenantLockedError("another Principal") from error
        raise AuthorizationDeniedError() from error
    safe_context_failures = {
        "profiling_run_not_running": "The Profiling Workflow Run is not running.",
        "profiling_scope_incomplete": "The Profiling selection is incomplete.",
        "profiling_scope_changed": "The selected Model Scope changed before execution.",
        "profiling_discovery_scope_missing": (
            "Every selected Object requires one active Metadata Discovery Scope assignment."
        ),
        "profiling_attributes_missing": (
            "Every selected Object requires at least one active Attribute."
        ),
        "profiling_context_too_large": "The Profiling Attribute selection is too large.",
        "invalid_request": "The Profiling execution request is invalid.",
    }
    code = message.partition(":")[0]
    if code in safe_context_failures:
        raise InvalidRequestError(safe_context_failures[code]) from error
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


def create_profiling_workflow_router(
    *,
    identity_provider: IdentityProvider,
    service: ProfilingWorkflowService,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/profiling/runs",
        tags=["profiling"],
    )

    async def execute_run(
        request: Request,
        response: Response,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        workflow_run_id: Annotated[int, Path(gt=0)],
        command: ExecuteProfilingRunRequest,
    ) -> ProfilingRunStart:
        principal = identity_provider.authenticate(request.headers)
        result = await service.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=command.expected_model_revision,
        )
        if result.changed and result.workflow_run_state == "running":
            response.status_code = status.HTTP_202_ACCEPTED
        else:
            response.status_code = status.HTTP_200_OK
        return result

    router.add_api_route(
        "/{workflow_run_id}/execute",
        execute_run,
        methods=["POST"],
        response_model=ProfilingRunStart,
        status_code=status.HTTP_202_ACCEPTED,
    )
    return router
