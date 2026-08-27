"""In-process execution of one exactly claimed notebook Workflow Run."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from .errors import (
    NotebookConfigurationError,
    NotebookDatabaseError,
)
from .notebook import NotebookWorkflowRequest
from .runtime import (
    NotebookDatabaseSettings,
    NotebookRuntimeSettings,
    notebook_database_connection,
)
from .shared_runtime import (
    create_notebook_workflow_database,
    run_coroutine_in_thread,
)
from .workflow_control import (
    NotebookPrincipal,
    NotebookWorkflowControlClient,
    WorkflowClaimResult,
    WorkflowCreateResult,
    WorkflowLeaseResult,
)

if TYPE_CHECKING:
    from gds_workbench_api.features.workflows.execution.repository import WorkflowClaimLease

_TERMINAL_STATES = frozenset({"completed", "completed_with_repair", "failed"})
_NOTEBOOK_CURSOR_KEY = b"gds-notebook-internal-read-key-v1"


@dataclass(frozen=True, slots=True)
class NotebookWorkflowExecutionResult:
    """Bounded result safe to display in a notebook cell."""

    workflow_run_id: int
    workflow: str
    state: str
    created: bool
    model_revision: int
    model_change_set_id: UUID | None = None
    model_change_set_status: str | None = None
    draft_revision: int | None = None
    candidate_digest: str | None = None
    failure_code: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "workflow_run_id": self.workflow_run_id,
            "workflow": self.workflow,
            "state": self.state,
            "created": self.created,
            "model_revision": self.model_revision,
        }
        for key, value in (
            ("model_change_set_id", self.model_change_set_id),
            ("model_change_set_status", self.model_change_set_status),
            ("draft_revision", self.draft_revision),
            ("candidate_digest", self.candidate_digest),
            ("failure_code", self.failure_code),
        ):
            if value is not None:
                result[key] = str(value) if isinstance(value, UUID) else value
        return result


class NotebookWorkflowClaimLeaseRepository:
    """Heartbeat one notebook claim through actor-free database wrappers."""

    def __init__(
        self,
        *,
        database_settings: NotebookDatabaseSettings,
        claim: WorkflowClaimResult,
    ) -> None:
        self._database_settings = database_settings
        self._claim = claim

    async def renew(
        self,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        lease_duration_seconds: int,
    ) -> WorkflowClaimLease:
        self._require_claim(workflow_run_id, workflow_run_claim_token)
        renewed = await asyncio.to_thread(self._renew, lease_duration_seconds)
        if renewed.heartbeat_time is None or renewed.expires_time is None:
            raise NotebookDatabaseError("The notebook Workflow claim could not be renewed.")
        from gds_workbench_api.features.workflows.execution.repository import (
            WorkflowClaimLease,
        )

        return WorkflowClaimLease(
            workflow_run_id=renewed.workflow_run_id,
            workflow_run_claim_heartbeat_time=renewed.heartbeat_time,
            workflow_run_claim_expires_time=renewed.expires_time,
        )

    async def release(
        self,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
    ) -> bool:
        self._require_claim(workflow_run_id, workflow_run_claim_token)
        result = await asyncio.to_thread(self._release)
        if not result.succeeded:
            raise NotebookDatabaseError("The notebook Workflow claim could not be released.")
        return True

    def _renew(self, lease_duration_seconds: int) -> WorkflowLeaseResult:
        with notebook_database_connection(self._database_settings) as connection:
            return NotebookWorkflowControlClient(connection).renew_workflow_run_claim(
                self._claim,
                lease_duration_seconds=lease_duration_seconds,
            )

    def _release(self) -> WorkflowLeaseResult:
        with notebook_database_connection(self._database_settings) as connection:
            return NotebookWorkflowControlClient(connection).release_workflow_run_claim(self._claim)

    def _require_claim(self, workflow_run_id: int, claim_token: UUID) -> None:
        if workflow_run_id != self._claim.workflow_run_id or claim_token != self._claim.claim_token:
            raise NotebookDatabaseError("The notebook Workflow claim does not match this Run.")


def execute_notebook_workflow(
    request: NotebookWorkflowRequest,
    *,
    settings: NotebookRuntimeSettings,
) -> NotebookWorkflowExecutionResult:
    """Run the async shared engine in a private thread, including inside IPython."""
    try:
        return run_coroutine_in_thread(lambda: _execute_notebook_workflow(request, settings))
    except (NotebookConfigurationError, NotebookDatabaseError):
        raise
    except Exception:
        raise NotebookDatabaseError(
            "Notebook Workflow execution failed without exposing runtime details."
        ) from None


async def _execute_notebook_workflow(
    request: NotebookWorkflowRequest,
    settings: NotebookRuntimeSettings,
) -> NotebookWorkflowExecutionResult:
    # Imports stay at the execution boundary. Tenant Lock and widget validation
    # do not import or start the App, FastAPI, or MCP server.
    from gds_etl_workbench.application.authorization import AuthorizationService
    from gds_workbench_api.capabilities import (
        load_default_agent_capabilities,
        select_agent_provider_capabilities,
    )
    from gds_workbench_api.features.workflows.execution import (
        WorkerRunResult,
        WorkflowClaimRunner,
        WorkflowExecutionClaim,
        WorkflowExecutionDispatcher,
    )
    from gds_workbench_api.features.workflows.execution.assembly import (
        create_workflow_runtime_services,
    )
    from gds_workbench_api.features.workflows.runs import DatabaseWorkflowRunService
    from gds_workbench_api.integrations.agents import DatabricksModelAuthentication
    from gds_workbench_api.integrations.agents.configuration import (
        AgentProviderConnection,
        AgentRuntimeConfiguration,
    )
    from gds_workbench_api.integrations.databricks import (
        create_databricks_execution_adapters,
    )

    database = create_notebook_workflow_database(settings.database)
    await database.open()
    services = None
    try:
        readiness = await database.readiness()
        if not readiness.ready:
            raise NotebookDatabaseError(
                "Notebook database execution provisioning is incomplete or unavailable."
            )

        principal, created = await asyncio.to_thread(
            _resolve_principal_and_create,
            settings.database,
            request,
        )
        authorizer = AuthorizationService()
        run_reader = DatabaseWorkflowRunService(
            database=database,
            authorizer=authorizer,
            cursor_signing_key=_NOTEBOOK_CURSOR_KEY,
        )
        if created.state in _TERMINAL_STATES:
            detail = await run_reader.read_run(
                _request_principal(principal),
                tenant_id=request.tenant_id,
                model_id=request.model_id,
                workflow_run_id=created.workflow_run_id,
            )
            return _execution_result(request, created, detail)

        agent_runtime, capabilities, authentications = _agent_runtime(
            request,
            settings,
            load_default_agent_capabilities(),
            select_agent_provider_capabilities,
            AgentProviderConnection,
            AgentRuntimeConfiguration,
            DatabricksModelAuthentication,
        )
        services = create_workflow_runtime_services(
            database=database,
            authorizer=authorizer,
            agent_runtime=agent_runtime,
            agent_capability_registry=capabilities,
            databricks_environment_code=principal.databricks_environment_code,
            databricks_execution=create_databricks_execution_adapters("remote"),
            provider_authentications=authentications,
        )
        claim = await asyncio.to_thread(
            _claim_created_run,
            settings.database,
            request,
            created,
            settings.workflow_lease_seconds,
        )
        execution_claim = WorkflowExecutionClaim.model_validate(
            {
                "workflow_run_id": claim.workflow_run_id,
                "tenant_id": claim.tenant_id,
                "model_id": claim.model_id,
                "model_revision": claim.model_revision,
                "model_workflow": claim.workflow,
                "workflow_execution_mode": claim.workflow_execution_mode,
                "correlation_id": claim.correlation_id,
                "actor_principal_type": claim.actor_principal_type,
                "actor_entra_tenant_id": claim.actor_entra_tenant_id,
                "actor_entra_object_id": claim.actor_entra_object_id,
                "workflow_run_claim_token": claim.claim_token,
                "workflow_run_claimed_time": claim.claimed_time,
                "workflow_run_claim_expires_time": claim.expires_time,
                "workflow_run_recovery_count": claim.recovery_count,
            },
            strict=False,
        )
        runner = WorkflowClaimRunner(
            claims=NotebookWorkflowClaimLeaseRepository(
                database_settings=settings.database,
                claim=claim,
            ),
            dispatcher=WorkflowExecutionDispatcher(services.execution_services()),
            lease_duration_seconds=settings.workflow_lease_seconds,
            heartbeat_interval_seconds=settings.workflow_heartbeat_seconds,
        )
        outcome = await runner.run(execution_claim)
        if outcome is not WorkerRunResult.COMPLETED:
            raise NotebookDatabaseError(
                "Notebook Workflow execution did not complete. Reuse the same "
                "IdempotencyKey after the active claim expires."
            )
        detail = await run_reader.read_run(
            execution_claim.principal,
            tenant_id=request.tenant_id,
            model_id=request.model_id,
            workflow_run_id=created.workflow_run_id,
        )
        if detail.workflow_run_state not in _TERMINAL_STATES:
            raise NotebookDatabaseError(
                "Notebook Workflow execution returned without a terminal Run state."
            )
        return _execution_result(request, created, detail)
    finally:
        try:
            if services is not None:
                await services.close()
        finally:
            await database.close()


def _resolve_principal_and_create(
    database_settings: NotebookDatabaseSettings,
    request: NotebookWorkflowRequest,
) -> tuple[NotebookPrincipal, WorkflowCreateResult]:
    with notebook_database_connection(database_settings) as connection:
        client = NotebookWorkflowControlClient(connection)
        principal = client.current_principal()
        return principal, client.create_workflow_run(request)


def _claim_created_run(
    database_settings: NotebookDatabaseSettings,
    request: NotebookWorkflowRequest,
    created: WorkflowCreateResult,
    lease_duration_seconds: int,
) -> WorkflowClaimResult:
    with notebook_database_connection(database_settings) as connection:
        return NotebookWorkflowControlClient(connection).start_and_claim_workflow_run(
            request,
            created,
            lease_duration_seconds=lease_duration_seconds,
        )


def _request_principal(principal: NotebookPrincipal) -> Any:
    from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

    return RequestPrincipal(
        actor_kind=ActorKind.WORKLOAD,
        entra_tenant_id=principal.entra_tenant_id,
        entra_object_id=principal.entra_object_id,
    )


def _agent_runtime(
    request: NotebookWorkflowRequest,
    settings: NotebookRuntimeSettings,
    capabilities: Any,
    select_capabilities: Callable[..., Any],
    connection_type: type[Any],
    configuration_type: type[Any],
    authentication_type: type[Any],
) -> tuple[Any, Any, dict[str, Any] | None]:
    selected_agent = request.create_payload.get("agent")
    if selected_agent is None:
        return (
            configuration_type(
                mode="fake",
                timeout_seconds=settings.agent_timeout_seconds,
                connections=(),
            ),
            capabilities,
            None,
        )
    if settings.databricks_model_endpoint is None:
        raise NotebookConfigurationError(
            "GDS_NOTEBOOK_DATABRICKS_MODEL_ENDPOINT is required for an agent Workflow."
        )
    if not isinstance(selected_agent, Mapping):
        raise NotebookConfigurationError(
            "Independent notebooks support the Databricks agent provider only."
        )
    selected_agent_mapping = cast(Mapping[str, object], selected_agent)
    if selected_agent_mapping.get("provider_code") != "databricks":
        raise NotebookConfigurationError(
            "Independent notebooks support the Databricks agent provider only."
        )
    connection = connection_type(
        provider_code="databricks",
        model_code="databricks-primary",
        model_endpoint=settings.databricks_model_endpoint,
        timeout_seconds=settings.agent_timeout_seconds,
    )
    return (
        configuration_type(
            mode="remote",
            timeout_seconds=settings.agent_timeout_seconds,
            connections=(connection,),
        ),
        select_capabilities(capabilities, provider_codes={"databricks"}),
        {"databricks": authentication_type(mode="notebook")},
    )


def _execution_result(
    request: NotebookWorkflowRequest,
    created: WorkflowCreateResult,
    detail: Any,
) -> NotebookWorkflowExecutionResult:
    workflow = (
        f"analysis_{request.analysis_operation}"
        if request.analysis_operation is not None
        else request.workflow
    )
    return NotebookWorkflowExecutionResult(
        workflow_run_id=created.workflow_run_id,
        workflow=workflow,
        state=detail.workflow_run_state,
        created=created.created,
        model_revision=created.model_revision,
        model_change_set_id=detail.model_change_set_id,
        model_change_set_status=detail.model_change_set_status,
        draft_revision=detail.draft_revision,
        candidate_digest=detail.candidate_digest,
        failure_code=detail.failure_code,
    )


__all__ = [
    "NotebookWorkflowClaimLeaseRepository",
    "NotebookWorkflowExecutionResult",
    "execute_notebook_workflow",
]
