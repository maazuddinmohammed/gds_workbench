from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from gds_workbench_api.capabilities import load_default_agent_capabilities

import gds_workbench_notebooks.workflow_execution as workflow_execution
from gds_workbench_notebooks.errors import (
    NotebookConfigurationError,
    NotebookDatabaseError,
)
from gds_workbench_notebooks.notebook import build_notebook_request, widget_specs
from gds_workbench_notebooks.runtime import (
    NotebookDatabaseSettings,
    NotebookRuntimeSettings,
)
from gds_workbench_notebooks.shared_runtime import (
    notebook_database_conninfo,
    run_coroutine_in_thread,
)
from gds_workbench_notebooks.workflow_control import (
    NotebookPrincipal,
    WorkflowClaimResult,
    WorkflowCreateResult,
)
from gds_workbench_notebooks.workflow_execution import (
    NotebookWorkflowClaimLeaseRepository,
    NotebookWorkflowExecutionResult,
)

_CORRELATION_ID = UUID("12345678-1234-4234-8234-123456789abc")
_TENANT_ID = UUID("22345678-1234-4234-8234-123456789abc")
_OBJECT_ID = UUID("32345678-1234-4234-8234-123456789abc")
_CLAIM_TOKEN = UUID("42345678-1234-4234-8234-123456789abc")
_NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _database() -> NotebookDatabaseSettings:
    return NotebookDatabaseSettings(
        host="workbench.postgres.database.azure.com",
        port=5432,
        database="gds_workbench",
        user="gds_notebook_runtime",
        password="fixture-password",
        sslmode="verify-full",
        connect_timeout_seconds=12,
        statement_timeout_seconds=45,
    )


def _settings() -> NotebookRuntimeSettings:
    return NotebookRuntimeSettings(
        database=_database(),
        workflow_lease_seconds=30,
        workflow_heartbeat_seconds=10,
        agent_timeout_seconds=120,
    )


def _request(workflow: str):
    values = {spec.name: spec.default for spec in widget_specs(workflow)}
    values.update(
        {
            "TenantID": "2",
            "ModelID": "3",
            "ExpectedModelRevision": "4",
            "SelectedObjectIDsJSON": "[11,12]",
            "IdempotencyKey": str(_CORRELATION_ID),
        }
    )
    return build_notebook_request(workflow, values)


def _claim() -> WorkflowClaimResult:
    return WorkflowClaimResult(
        workflow_run_id=71,
        tenant_id=2,
        model_id=3,
        model_revision=4,
        workflow="profiling",
        workflow_execution_mode=None,
        correlation_id=_CORRELATION_ID,
        actor_principal_type="service_principal",
        actor_entra_tenant_id=_TENANT_ID,
        actor_entra_object_id=_OBJECT_ID,
        claim_token=_CLAIM_TOKEN,
        claimed_time=_NOW,
        expires_time=_NOW + timedelta(seconds=30),
        recovery_count=0,
    )


def test_execution_result_is_bounded_and_omits_empty_fields() -> None:
    result = NotebookWorkflowExecutionResult(
        workflow_run_id=71,
        workflow="conceptual",
        state="completed",
        created=True,
        model_revision=4,
        model_change_set_id=UUID("52345678-1234-4234-8234-123456789abc"),
        model_change_set_status="validated",
        draft_revision=3,
        candidate_digest="a" * 64,
    )

    assert result.as_dict() == {
        "workflow_run_id": 71,
        "workflow": "conceptual",
        "state": "completed",
        "created": True,
        "model_revision": 4,
        "model_change_set_id": "52345678-1234-4234-8234-123456789abc",
        "model_change_set_status": "validated",
        "draft_revision": 3,
        "candidate_digest": "a" * 64,
        "draft_review": {
            "ready": True,
            "message": "Draft is ready to review in the workbench. Apply remains explicit.",
        },
    }
    assert str(_CLAIM_TOKEN) not in repr(result)


def test_terminal_idempotent_replay_returns_the_existing_run_without_claiming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import gds_workbench_api.features.workflows.execution.assembly as assembly
    import gds_workbench_api.features.workflows.runs as runs

    request = _request("profiling")
    principal = NotebookPrincipal(
        display_name="Databricks Notebook Runtime",
        principal_type="service_principal",
        databricks_environment_code="PROD",
        entra_tenant_id=_TENANT_ID,
        entra_object_id=_OBJECT_ID,
    )
    created = WorkflowCreateResult(
        workflow_run_id=71,
        workflow="profiling",
        state="completed",
        created=False,
        correlation_id=_CORRELATION_ID,
        model_revision=4,
        selected_scope_count=2,
        prompt_snapshot_count=0,
        created_time=_NOW,
    )
    detail = SimpleNamespace(
        workflow_run_state="completed",
        model_change_set_id=None,
        model_change_set_status=None,
        draft_revision=None,
        candidate_digest=None,
        failure_code=None,
    )

    class Database:
        def __init__(self) -> None:
            self.opened = False
            self.closed = False

        async def open(self) -> None:
            self.opened = True

        async def readiness(self) -> object:
            return SimpleNamespace(ready=True)

        async def close(self) -> None:
            self.closed = True

    class RunReader:
        calls: list[tuple[object, dict[str, int]]] = []

        def __init__(self, *, database, authorizer, cursor_signing_key) -> None:
            assert database is runtime_database
            assert authorizer is not None
            assert cursor_signing_key

        async def read_run(self, received_principal, **values):
            self.calls.append((received_principal, values))
            return detail

    runtime_database = Database()
    monkeypatch.setattr(
        workflow_execution,
        "create_notebook_workflow_database",
        lambda _settings: runtime_database,
    )
    monkeypatch.setattr(
        workflow_execution,
        "_resolve_principal_and_create",
        lambda _settings, received: (
            (principal, created)
            if received is request
            else pytest.fail("unexpected Workflow request")
        ),
    )
    monkeypatch.setattr(
        workflow_execution,
        "_claim_created_run",
        lambda *_args, **_kwargs: pytest.fail("terminal replay must not claim"),
    )
    monkeypatch.setattr(
        assembly,
        "create_workflow_runtime_services",
        lambda **_kwargs: pytest.fail("terminal replay must not assemble executors"),
    )
    monkeypatch.setattr(runs, "DatabaseWorkflowRunService", RunReader)

    result = workflow_execution.execute_notebook_workflow(
        request,
        settings=_settings(),
    )

    assert result == NotebookWorkflowExecutionResult(
        workflow_run_id=71,
        workflow="profiling",
        state="completed",
        created=False,
        model_revision=4,
    )
    assert runtime_database.opened is True
    assert runtime_database.closed is True
    assert len(RunReader.calls) == 1
    received_principal, values = RunReader.calls[0]
    assert received_principal.entra_tenant_id == _TENANT_ID
    assert received_principal.entra_object_id == _OBJECT_ID
    assert values == {"tenant_id": 2, "model_id": 3, "workflow_run_id": 71}


@pytest.mark.parametrize(
    ("durable_state", "failure_code"),
    (
        ("running", None),
        ("failed", "workflow_run_context_unavailable"),
    ),
)
def test_unavailable_claim_returns_the_refreshed_durable_run(
    monkeypatch: pytest.MonkeyPatch,
    durable_state: str,
    failure_code: str | None,
) -> None:
    import gds_workbench_api.features.workflows.execution.assembly as assembly
    import gds_workbench_api.features.workflows.runs as runs

    request = _request("profiling")
    principal = NotebookPrincipal(
        display_name="Databricks Notebook Runtime",
        principal_type="service_principal",
        databricks_environment_code="PROD",
        entra_tenant_id=_TENANT_ID,
        entra_object_id=_OBJECT_ID,
    )
    initial = WorkflowCreateResult(
        workflow_run_id=71,
        workflow="profiling",
        state="queued",
        created=True,
        correlation_id=_CORRELATION_ID,
        model_revision=4,
        selected_scope_count=2,
        prompt_snapshot_count=0,
        created_time=_NOW,
    )
    refreshed = WorkflowCreateResult(
        workflow_run_id=71,
        workflow="profiling",
        state=durable_state,
        created=False,
        correlation_id=_CORRELATION_ID,
        model_revision=4,
        selected_scope_count=2,
        prompt_snapshot_count=0,
        created_time=_NOW,
    )
    detail = SimpleNamespace(
        workflow_run_state=durable_state,
        model_change_set_id=None,
        model_change_set_status=None,
        draft_revision=None,
        candidate_digest=None,
        failure_code=failure_code,
    )

    class Database:
        async def open(self) -> None:
            pass

        async def readiness(self) -> object:
            return SimpleNamespace(ready=True)

        async def close(self) -> None:
            pass

    class RunReader:
        def __init__(self, *, database, authorizer, cursor_signing_key) -> None:
            assert database is runtime_database
            assert authorizer is not None
            assert cursor_signing_key

        async def read_run(self, received_principal, **values):
            assert received_principal.entra_tenant_id == _TENANT_ID
            assert values == {"tenant_id": 2, "model_id": 3, "workflow_run_id": 71}
            return detail

    runtime_database = Database()
    resolutions = iter(((principal, initial), (principal, refreshed)))
    monkeypatch.setattr(
        workflow_execution,
        "create_notebook_workflow_database",
        lambda _settings: runtime_database,
    )
    monkeypatch.setattr(
        workflow_execution,
        "_resolve_principal_and_create",
        lambda _settings, received: (
            next(resolutions) if received is request else pytest.fail("unexpected Workflow request")
        ),
    )
    monkeypatch.setattr(workflow_execution, "_claim_created_run", lambda *_args: None)
    monkeypatch.setattr(
        assembly,
        "create_workflow_runtime_services",
        lambda **_kwargs: pytest.fail("an unclaimed Run must not assemble executors"),
    )
    monkeypatch.setattr(runs, "DatabaseWorkflowRunService", RunReader)

    result = workflow_execution.execute_notebook_workflow(request, settings=_settings())

    assert result == NotebookWorkflowExecutionResult(
        workflow_run_id=71,
        workflow="profiling",
        state=durable_state,
        created=False,
        model_revision=4,
        failure_code=failure_code,
    )


def test_new_run_is_exactly_claimed_executed_and_returned_after_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import gds_workbench_api.features.workflows.execution.assembly as assembly
    import gds_workbench_api.features.workflows.runs as runs
    import gds_workbench_api.integrations.databricks as databricks_integration

    request = _request("profiling")
    principal = NotebookPrincipal(
        display_name="Databricks Notebook Runtime",
        principal_type="service_principal",
        databricks_environment_code="PROD",
        entra_tenant_id=_TENANT_ID,
        entra_object_id=_OBJECT_ID,
    )
    created = WorkflowCreateResult(
        workflow_run_id=71,
        workflow="profiling",
        state="queued",
        created=True,
        correlation_id=_CORRELATION_ID,
        model_revision=4,
        selected_scope_count=2,
        prompt_snapshot_count=0,
        created_time=_NOW,
    )
    claim = _claim()
    change_set_id = UUID("52345678-1234-4234-8234-123456789abc")
    detail = SimpleNamespace(
        workflow_run_state="completed",
        model_change_set_id=change_set_id,
        model_change_set_status="validated",
        draft_revision=3,
        candidate_digest="a" * 64,
        failure_code=None,
    )
    events: list[str] = []

    class Database:
        async def open(self) -> None:
            events.append("database_opened")

        async def readiness(self) -> object:
            events.append("database_ready")
            return SimpleNamespace(ready=True)

        async def close(self) -> None:
            events.append("database_closed")

    class Executor:
        async def execute_started(self, received_principal, **values):
            assert received_principal.entra_tenant_id == _TENANT_ID
            assert received_principal.entra_object_id == _OBJECT_ID
            assert values == {
                "tenant_id": 2,
                "model_id": 3,
                "workflow_run_id": 71,
                "expected_model_revision": 4,
                "workflow_run_claim_token": _CLAIM_TOKEN,
            }
            events.append("workflow_executed")

    class Services:
        def __init__(self) -> None:
            self.executor = Executor()

        def execution_services(self):
            return SimpleNamespace(
                profiling=self.executor,
                analysis_inference=self.executor,
                analysis_validation=self.executor,
                conceptual=self.executor,
                logical=self.executor,
                dimensional=self.executor,
                mapping=self.executor,
                code_generation=self.executor,
            )

        async def close(self) -> None:
            events.append("services_closed")

    class RunReader:
        def __init__(self, *, database, authorizer, cursor_signing_key) -> None:
            assert database is runtime_database
            assert authorizer is not None
            assert cursor_signing_key

        async def read_run(self, received_principal, **values):
            assert received_principal.entra_tenant_id == _TENANT_ID
            assert received_principal.entra_object_id == _OBJECT_ID
            assert values == {"tenant_id": 2, "model_id": 3, "workflow_run_id": 71}
            events.append("run_read")
            return detail

    runtime_database = Database()
    services = Services()
    adapter_marker = object()
    assembly_values: dict[str, object] = {}
    claim_values: list[tuple[object, object, int]] = []
    monkeypatch.setattr(
        workflow_execution,
        "create_notebook_workflow_database",
        lambda _settings: runtime_database,
    )
    monkeypatch.setattr(
        workflow_execution,
        "_resolve_principal_and_create",
        lambda _settings, received: (
            (principal, created)
            if received is request
            else pytest.fail("unexpected Workflow request")
        ),
    )

    def exact_claim(database_settings, received_request, received_created, lease_seconds):
        assert database_settings is _settings_instance.database
        assert received_request is request
        assert received_created is created
        claim_values.append((received_request, received_created, lease_seconds))
        return claim

    monkeypatch.setattr(workflow_execution, "_claim_created_run", exact_claim)

    def assemble(**values):
        assembly_values.update(values)
        return services

    monkeypatch.setattr(assembly, "create_workflow_runtime_services", assemble)
    monkeypatch.setattr(runs, "DatabaseWorkflowRunService", RunReader)
    monkeypatch.setattr(
        databricks_integration,
        "create_databricks_execution_adapters",
        lambda mode: adapter_marker if mode == "remote" else pytest.fail("unexpected mode"),
    )
    _settings_instance = _settings()

    result = workflow_execution.execute_notebook_workflow(
        request,
        settings=_settings_instance,
    )

    assert result == NotebookWorkflowExecutionResult(
        workflow_run_id=71,
        workflow="profiling",
        state="completed",
        created=True,
        model_revision=4,
        model_change_set_id=change_set_id,
        model_change_set_status="validated",
        draft_revision=3,
        candidate_digest="a" * 64,
    )
    assert claim_values == [(request, created, 30)]
    assert assembly_values["database"] is runtime_database
    assert assembly_values["databricks_environment_code"] == "PROD"
    assert assembly_values["databricks_execution"] is adapter_marker
    assert assembly_values["agent_runtime"].mode == "fake"
    assert events == [
        "database_opened",
        "database_ready",
        "workflow_executed",
        "run_read",
        "services_closed",
        "database_closed",
    ]


@pytest.mark.asyncio
async def test_private_thread_bridge_works_while_an_event_loop_is_running() -> None:
    async def operation() -> int:
        return 7

    assert run_coroutine_in_thread(operation) == 7


@pytest.mark.asyncio
async def test_claim_lease_calls_only_the_fixed_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = _claim()
    actions: list[tuple[str, int]] = []

    @contextmanager
    def connection(_settings):
        yield object()

    class Client:
        def __init__(self, _connection) -> None:
            pass

        def renew_workflow_run_claim(self, received, *, lease_duration_seconds):
            assert received is claim
            actions.append(("renew", lease_duration_seconds))
            return type(
                "Lease",
                (),
                {
                    "workflow_run_id": 71,
                    "heartbeat_time": _NOW + timedelta(seconds=10),
                    "expires_time": _NOW + timedelta(seconds=40),
                    "succeeded": True,
                },
            )()

        def release_workflow_run_claim(self, received):
            assert received is claim
            actions.append(("release", 0))
            return type("Lease", (), {"succeeded": True})()

    monkeypatch.setattr(workflow_execution, "notebook_database_connection", connection)
    monkeypatch.setattr(workflow_execution, "NotebookWorkflowControlClient", Client)
    repository = NotebookWorkflowClaimLeaseRepository(
        database_settings=_database(),
        claim=claim,
    )

    await repository.renew(
        workflow_run_id=71,
        workflow_run_claim_token=_CLAIM_TOKEN,
        lease_duration_seconds=30,
    )
    assert await repository.release(
        workflow_run_id=71,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )
    assert actions == [("renew", 30), ("release", 0)]

    with pytest.raises(NotebookDatabaseError, match="does not match"):
        await repository.renew(
            workflow_run_id=72,
            workflow_run_claim_token=_CLAIM_TOKEN,
            lease_duration_seconds=30,
        )


def test_agent_runtime_uses_registry_deployment_and_databricks_provider_only() -> None:
    class Connection:
        def __init__(self, **values) -> None:
            self.values = values
            self.provider_code = values["provider_code"]
            self.model_code = values["model_code"]

    class Configuration:
        def __init__(self, **values) -> None:
            self.values = values
            self.connections = values["connections"]

    class Authentication:
        def __init__(self, **values) -> None:
            self.values = values

    request = _request("conceptual")
    foundry_agent = dict(request.create_payload["agent"])
    foundry_agent["provider_code"] = "microsoft_foundry"
    with pytest.raises(NotebookConfigurationError, match="Databricks agent provider only"):
        workflow_execution._agent_runtime(
            replace(
                request,
                create_payload={**request.create_payload, "agent": foundry_agent},
            ),
            _settings(),
            load_default_agent_capabilities(),
            lambda capabilities, **_kwargs: capabilities,
            Connection,
            Configuration,
            Authentication,
        )

    configuration, capabilities, authentications = workflow_execution._agent_runtime(
        request,
        _settings(),
        load_default_agent_capabilities(),
        lambda capabilities, **kwargs: (f"selected-{capabilities}", kwargs),
        Connection,
        Configuration,
        Authentication,
    )
    assert configuration.values["mode"] == "remote"
    assert configuration.values["connections"][0].values == {
        "provider_code": "databricks",
        "model_code": "databricks-primary",
        "model_endpoint": "databricks-gpt-oss-120b",
        "timeout_seconds": 120,
    }
    assert capabilities == (
        f"selected-{load_default_agent_capabilities()}",
        {"configured_models": {("databricks", "databricks-primary")}},
    )
    assert authentications["databricks"].values == {"mode": "notebook"}


def test_agent_runtime_uses_the_selected_registered_model_endpoint() -> None:
    class Connection:
        def __init__(self, **values) -> None:
            self.values = values
            self.provider_code = values["provider_code"]
            self.model_code = values["model_code"]

    class Configuration:
        def __init__(self, **values) -> None:
            self.values = values
            self.connections = values["connections"]

    class Authentication:
        def __init__(self, **values) -> None:
            self.values = values

    request = _request("conceptual")
    agent = dict(request.create_payload["agent"])
    agent["model_code"] = "databricks-secondary"
    request = replace(
        request,
        create_payload={**request.create_payload, "agent": agent},
    )
    registry = load_default_agent_capabilities()
    primary = next(model for model in registry.models if model.code == "databricks-primary")
    secondary = primary.model_copy(
        update={
            "code": "databricks-secondary",
            "deployment_name": "gds-secondary",
        }
    )
    capabilities_registry = registry.model_copy(update={"models": (*registry.models, secondary)})

    configuration, capabilities, _authentications = workflow_execution._agent_runtime(
        request,
        _settings(),
        capabilities_registry,
        lambda capabilities, **kwargs: (capabilities, kwargs),
        Connection,
        Configuration,
        Authentication,
    )

    assert configuration.connections[0].values["model_code"] == "databricks-secondary"
    assert configuration.connections[0].values["model_endpoint"] == "gds-secondary"
    assert capabilities == (
        capabilities_registry,
        {"configured_models": {("databricks", "databricks-secondary")}},
    )


def test_agent_runtime_rejects_a_selected_model_missing_from_the_registry() -> None:
    request = _request("conceptual")
    agent = dict(request.create_payload["agent"])
    agent["model_code"] = "databricks-secondary"
    request = replace(
        request,
        create_payload={**request.create_payload, "agent": agent},
    )
    capabilities = load_default_agent_capabilities()

    with pytest.raises(
        NotebookConfigurationError,
        match="not registered",
    ):
        workflow_execution._agent_runtime(
            request,
            _settings(),
            capabilities,
            lambda value, **_kwargs: value,
            object,
            object,
            object,
        )


def test_deterministic_runtime_needs_no_model_registry_connection() -> None:
    class Configuration:
        def __init__(self, **values) -> None:
            self.values = values

    configuration, capabilities, authentications = workflow_execution._agent_runtime(
        _request("profiling"),
        _settings(),
        "capabilities",
        lambda capabilities, **_kwargs: capabilities,
        object,
        Configuration,
        object,
    )

    assert configuration.values == {
        "mode": "fake",
        "timeout_seconds": 120,
        "connections": (),
    }
    assert capabilities == "capabilities"
    assert authentications is None


def test_conninfo_is_built_from_explicit_fields_and_not_environment() -> None:
    conninfo = notebook_database_conninfo(_database())

    assert "host=workbench.postgres.database.azure.com" in conninfo
    assert "user=gds_notebook_runtime" in conninfo
    assert "password=fixture-password" in conninfo
    assert "gds_workbench_databricks_notebook_runtime" in conninfo
    assert "DATABASE_URL" not in conninfo


def test_execution_source_starts_no_app_or_mcp_server() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "gds_workbench_notebooks" / "workflow_execution.py"
    ).read_text()

    for forbidden in (
        "uvicorn.run",
        "FastAPI(",
        "MCPServer(",
        "run_mcp",
        "AppName",
        "GDS_WEB_",
    ):
        assert forbidden not in source
