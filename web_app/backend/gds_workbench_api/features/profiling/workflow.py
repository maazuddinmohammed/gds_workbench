"""Governed orchestration for deterministic bulk Profiling runs."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Annotated, Any, Never, Protocol
from uuid import UUID

from fastapi import APIRouter, Path, Request, Response, status
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DatabricksConnectionConfigurationError,
    DependencyUnavailableError,
    InvalidRequestError,
    TenantLockedError,
    TenantLockRequiredError,
    TenantWorkflowConflictError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, WriteTransaction
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.features.models import ModelRevisionConflictError
from gds_workbench_api.features.workflows.execution.fence import (
    assert_workflow_run_claim,
)
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError
from gds_workbench_runtime.profiling.execution import (
    ProfileAttribute,
    ProfileObject,
)
from gds_workbench_runtime.profiling.workflow import (
    ProfilingCommitResult,
    ProfilingExecutionContext,
    ProfilingExecutionTarget,
    ProfilingRunStart,
    ProfilingWorkflowOrchestrator,
    ProfilingWorkflowRepository,
)

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


class ExecuteProfilingRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)


class ProfilingWorkflowDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


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
            async with self._database.write_transaction(
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
            catalog, schema, table, batch_attribute_name, attribute_names = (
                _resolve_profiling_relation(object_rows)
            )
            target_object = ProfileObject(
                object_id=_required_int(header, "object_id"),
                connection_id=connection_id,
                catalog=catalog,
                schema=schema,
                table=table,
                batch_attribute_name=batch_attribute_name,
                attributes=tuple(
                    ProfileAttribute(
                        attribute_id=_required_int(row, "attribute_id"),
                        name=attribute_names[index],
                        data_type=_required_text(row, "attribute_data_type"),
                    )
                    for index, row in enumerate(object_rows)
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


async def _require_profiling_binding(
    transaction: WriteTransaction,
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


def _resolve_profiling_relation(
    rows: list[dict[str, Any]],
) -> tuple[str, str, str, str | None, tuple[str, ...]]:
    """Resolve the only allowed Databricks relation for Source or Bronze metadata."""

    if not rows:
        raise DependencyUnavailableError()
    header = rows[0]
    zone = _required_text(header, "zone_code").strip().casefold()
    if zone == "source":
        if header.get("has_foreign_catalog") is not True:
            raise InvalidRequestError("Source Profiling requires an enabled foreign catalog.")
        catalog = _required_foreign_catalog_text(header, "foreign_catalog")
        schema = _required_foreign_catalog_text(header, "fc_object_schema")
        table = _required_foreign_catalog_text(header, "fc_object_name")
        names = tuple(_required_foreign_catalog_text(row, "fc_attribute_name") for row in rows)
    elif zone == "bronze":
        catalog = _required_text(header, "relation_catalog")
        schema = _required_text(header, "object_schema")
        table = _required_text(header, "object_name")
        names = tuple(_required_text(row, "attribute_name") for row in rows)
    else:
        raise InvalidRequestError(
            "Profiling supports only Source or Bronze Model Input Scope Objects."
        )

    expected_object_fields = (
        ("relation_catalog", catalog),
        ("relation_schema", schema),
        ("relation_object", table),
    )
    batch_names: list[str] = []
    for row, name in zip(rows, names, strict=True):
        if _required_text(row, "zone_code").strip().casefold() != zone:
            raise DependencyUnavailableError()
        if any(_required_text(row, key) != expected for key, expected in expected_object_fields):
            raise DependencyUnavailableError()
        if _required_text(row, "relation_attribute") != name:
            raise DependencyUnavailableError()
        is_batch = row.get("is_batch_attribute")
        if not isinstance(is_batch, bool):
            raise DependencyUnavailableError()
        if is_batch:
            batch_names.append(name)
    if len(batch_names) > 1:
        raise DependencyUnavailableError()
    return catalog, schema, table, batch_names[0] if batch_names else None, names


def _required_foreign_catalog_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequestError(
            "Source Profiling requires complete foreign-catalog Object and Attribute metadata."
        )
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
        "profiling_scope_changed": "The selected Model Input Scope changed before execution.",
        "profiling_relation_unavailable": (
            "Every selected Object must be an eligible Source foreign-catalog or Bronze "
            "relation owned by the Model Tenant."
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


__all__ = [
    "DatabaseProfilingWorkflowRepository",
    "ExecuteProfilingRunRequest",
    "ProfilingCommitResult",
    "ProfilingExecutionContext",
    "ProfilingExecutionTarget",
    "ProfilingRunStart",
    "ProfilingWorkflowDatabase",
    "ProfilingWorkflowOrchestrator",
    "ProfilingWorkflowRepository",
    "ProfilingWorkflowService",
    "create_profiling_workflow_router",
]
