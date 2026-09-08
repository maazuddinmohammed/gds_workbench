from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import get_ident
from types import SimpleNamespace
from uuid import UUID

import pytest
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.features.workflows.usage.read_service import (
    WorkflowCostEstimate,
    WorkflowTokenUsageSummary,
)

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
        "token_usage": WorkflowTokenUsageSummary().model_dump(mode="json"),
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


@pytest.mark.parametrize("workflow", ["profiling", "metadata_enrichment"])
def test_terminal_idempotent_replay_returns_the_existing_run_without_claiming(
    monkeypatch: pytest.MonkeyPatch,
    workflow: str,
) -> None:
    import gds_workbench_api.features.workflows.execution.assembly as assembly
    import gds_workbench_api.features.workflows.runs as runs

    request = _request(workflow)
    principal = NotebookPrincipal(
        display_name="Databricks Notebook Runtime",
        principal_type="service_principal",
        databricks_environment_code="PROD",
        entra_tenant_id=_TENANT_ID,
        entra_object_id=_OBJECT_ID,
    )
    created = WorkflowCreateResult(
        workflow_run_id=71,
        workflow=workflow,
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
        token_usage=WorkflowTokenUsageSummary(
            status="complete",
            request_count=2,
            reported_request_count=2,
            input_tokens=120,
            output_tokens=18,
            total_tokens=138,
            cost_estimate=WorkflowCostEstimate(
                status="estimated",
                amount="0.00000138",
                priced_request_count=2,
                pricing_bases=("Fixture USD schedule",),
            ),
        ),
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

    counts = {"applied": 3, "unavailable": 1}
    field_counts = {
        "object_description": 1,
        "attribute_description": 1,
        "attribute_inferred_data_type": 1,
    }
    from gds_workbench_api.features.metadata_enrichment import read_service

    class EnrichmentReader:
        def __init__(self, *, database, authorizer):
            assert database is runtime_database
            assert authorizer is not None

        async def read_results(self, received_principal, **values):
            assert workflow == "metadata_enrichment"
            assert received_principal.entra_object_id == _OBJECT_ID
            assert values == {
                "tenant_id": 2,
                "model_id": 3,
                "workflow_run_id": 71,
                "limit": 1,
            }
            return SimpleNamespace(
                counts=counts,
                applied_field_counts=field_counts,
                results=[{"applied_value": "must not appear in notebook output"}],
            )

    monkeypatch.setattr(read_service, "DatabaseMetadataEnrichmentReadService", EnrichmentReader)
    result = workflow_execution.execute_notebook_workflow(
        request,
        settings=_settings(),
    )

    assert result == NotebookWorkflowExecutionResult(
        workflow_run_id=71,
        workflow=workflow,
        state="completed",
        created=False,
        model_revision=4,
        token_usage=detail.token_usage,
        metadata_enrichment_counts=counts if workflow == "metadata_enrichment" else None,
        metadata_enrichment_applied_field_counts=(
            field_counts if workflow == "metadata_enrichment" else None
        ),
    )
    output = result.as_dict()
    assert output["token_usage"] == detail.token_usage.model_dump(mode="json")
    assert "draft_review" not in output
    assert "must not appear" not in repr(output)
    if workflow == "metadata_enrichment":
        assert output["metadata_enrichment"]["applied_fields"] == field_counts
        assert output["metadata_enrichment"]["outcomes"] == counts
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
        token_usage=WorkflowTokenUsageSummary(
            status="partial" if durable_state == "failed" else "recording",
            request_count=1,
            pending_request_count=1,
        ),
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
        token_usage=detail.token_usage,
    )
    assert result.as_dict()["token_usage"] == detail.token_usage.model_dump(mode="json")


@pytest.mark.parametrize("workflow", ["profiling", "conceptual"])
def test_new_run_is_exactly_claimed_executed_and_returned_after_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    workflow: str,
) -> None:
    import gds_workbench_api.features.workflows.execution.assembly as assembly
    import gds_workbench_api.features.workflows.runs as runs
    import gds_workbench_api.integrations.databricks as databricks_integration

    request = _request(workflow)
    principal = NotebookPrincipal(
        display_name="Databricks Notebook Runtime",
        principal_type="service_principal",
        databricks_environment_code="PROD",
        entra_tenant_id=_TENANT_ID,
        entra_object_id=_OBJECT_ID,
    )
    created = WorkflowCreateResult(
        workflow_run_id=71,
        workflow=workflow,
        state="queued",
        created=True,
        correlation_id=_CORRELATION_ID,
        model_revision=4,
        selected_scope_count=2,
        prompt_snapshot_count=0,
        created_time=_NOW,
    )
    claim = replace(
        _claim(),
        workflow=workflow,
        workflow_execution_mode=request.create_payload["workflow_execution_mode"],
    )
    change_set_id = UUID("52345678-1234-4234-8234-123456789abc")
    detail = SimpleNamespace(
        workflow_run_state="completed",
        model_change_set_id=change_set_id,
        model_change_set_status="validated",
        draft_revision=3,
        candidate_digest="a" * 64,
        failure_code=None,
        token_usage=WorkflowTokenUsageSummary(
            status="complete",
            request_count=1,
            reported_request_count=1,
            input_tokens=12,
            output_tokens=5,
            total_tokens=17,
        ),
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
                usage_recorder=None,
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
    if workflow == "conceptual":
        _settings_instance = replace(_settings_instance, agent_runtime=_foundry_runtime())

    result = workflow_execution.execute_notebook_workflow(
        request,
        settings=_settings_instance,
    )

    assert result == NotebookWorkflowExecutionResult(
        workflow_run_id=71,
        workflow=workflow,
        state="completed",
        created=True,
        model_revision=4,
        model_change_set_id=change_set_id,
        model_change_set_status="validated",
        draft_revision=3,
        candidate_digest="a" * 64,
        token_usage=detail.token_usage,
    )
    assert result.as_dict()["token_usage"] == detail.token_usage.model_dump(mode="json")
    assert claim_values == [(request, created, 30)]
    assert assembly_values["database"] is runtime_database
    assert assembly_values["databricks_environment_code"] == "PROD"
    assert assembly_values["databricks_execution"] is adapter_marker
    assert assembly_values["agent_runtime"].mode == (
        "remote" if workflow == "conceptual" else "fake"
    )
    assert assembly_values["provider_authentications"] is None
    if workflow == "conceptual":
        assert len(assembly_values["agent_runtime"].connections) == 1
        assert assembly_values["agent_runtime"].connections[0].provider_code == "microsoft_foundry"
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
    caller_thread = get_ident()

    async def operation() -> int:
        assert get_ident() != caller_thread
        return 7

    assert run_coroutine_in_thread(operation) == 7


@pytest.mark.parametrize("failure", [ValueError("fixture"), asyncio.CancelledError()])
@pytest.mark.parametrize("fail_in_factory", [False, True])
def test_private_thread_bridge_propagates_original_failure(
    failure: BaseException, fail_in_factory: bool
) -> None:
    async def operation() -> None:
        raise failure

    def factory():
        if fail_in_factory:
            raise failure
        return operation()

    with pytest.raises(type(failure)) as caught:
        run_coroutine_in_thread(factory)
    assert caught.value is failure


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


def _foundry_runtime(capabilities=None):
    from gds_workbench_api.integrations.agents.configuration import AgentRuntimeConfiguration

    return AgentRuntimeConfiguration.from_environment(
        {
            "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": "https://fixture.openai.azure.com/openai/v1/",
            "GDS_WEB_FOUNDRY_API_KEY": "fixture-foundry-key",
        },
        production=True,
        capabilities=capabilities,
    )


def test_agent_runtime_uses_only_the_selected_registered_foundry_deployment() -> None:
    registry = load_default_agent_capabilities()
    primary = next(model for model in registry.models if model.code == "foundry-primary")
    secondary = primary.model_copy(
        update={"code": "foundry-secondary", "deployment_name": "gds-secondary"}
    )
    registry = registry.model_copy(update={"models": (*registry.models, secondary)})
    request = _request("conceptual")
    agent = {**request.create_payload["agent"], "model_code": "foundry-secondary"}
    request = replace(request, create_payload={**request.create_payload, "agent": agent})
    settings = replace(_settings(), agent_runtime=_foundry_runtime(registry))

    configuration, capabilities = workflow_execution._agent_runtime(request, settings, registry)

    assert configuration.mode == "remote"
    assert len(configuration.connections) == 1
    connection = configuration.connections[0]
    assert connection.provider_code == "microsoft_foundry"
    assert connection.model_code == "foundry-secondary"
    assert connection.model_endpoint == "gds-secondary"
    assert connection.foundry_api_key.get_secret_value() == "fixture-foundry-key"
    assert [model.code for model in capabilities.models] == ["foundry-secondary"]
    assert "fixture-foundry-key" not in repr(settings)


@pytest.mark.parametrize(
    "changed", [{"provider_code": "databricks"}, {"sdk_code": "langchain_create_agent"}]
)
def test_agent_runtime_rejects_retired_integrations(changed) -> None:
    request = _request("conceptual")
    request = replace(
        request,
        create_payload={
            **request.create_payload,
            "agent": {**request.create_payload["agent"], **changed},
        },
    )
    with pytest.raises(
        NotebookConfigurationError, match="OpenAI Agents SDK with Microsoft Foundry"
    ):
        workflow_execution._agent_runtime(request, _settings(), load_default_agent_capabilities())


def test_agent_runtime_rejects_a_selected_model_missing_from_the_registry() -> None:
    request = _request("conceptual")
    request = replace(
        request,
        create_payload={
            **request.create_payload,
            "agent": {**request.create_payload["agent"], "model_code": "unregistered"},
        },
    )
    with pytest.raises(NotebookConfigurationError, match="not registered"):
        workflow_execution._agent_runtime(request, _settings(), load_default_agent_capabilities())


def test_agent_runtime_requires_foundry_before_claiming() -> None:
    with pytest.raises(NotebookConfigurationError, match="Configure Foundry authentication"):
        workflow_execution._agent_runtime(
            _request("conceptual"), _settings(), load_default_agent_capabilities()
        )


def test_agent_runtime_rejects_stale_deployment_configuration() -> None:
    registry = load_default_agent_capabilities()
    configured = _foundry_runtime(registry)
    first = configured.connections[0].model_copy(update={"model_endpoint": "retired-deployment"})
    configured = configured.model_copy(update={"connections": (first,)})
    with pytest.raises(NotebookConfigurationError, match="not configured"):
        workflow_execution._agent_runtime(
            _request("conceptual"), replace(_settings(), agent_runtime=configured), registry
        )


def test_deterministic_runtime_needs_no_model_registry_connection() -> None:
    registry = load_default_agent_capabilities()
    configuration, capabilities = workflow_execution._agent_runtime(
        _request("profiling"), _settings(), registry
    )
    assert configuration.mode == "fake"
    assert configuration.timeout_seconds == 120
    assert configuration.connections == ()
    assert capabilities is registry


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


def test_missing_foundry_configuration_does_not_take_a_run_claim(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    import gds_workbench_api.features.workflows.runs as runs

    request = _request("conceptual")
    database = SimpleNamespace(
        open=AsyncMock(),
        close=AsyncMock(),
        readiness=AsyncMock(return_value=SimpleNamespace(ready=True)),
    )
    monkeypatch.setattr(workflow_execution, "create_notebook_workflow_database", lambda _: database)
    monkeypatch.setattr(
        workflow_execution,
        "_resolve_principal_and_create",
        lambda *_: (object(), SimpleNamespace(state="queued")),
    )
    monkeypatch.setattr(runs, "DatabaseWorkflowRunService", lambda **_: object())
    monkeypatch.setattr(
        workflow_execution, "_claim_created_run", lambda *_: pytest.fail("must not claim")
    )

    with pytest.raises(NotebookConfigurationError, match="Configure Foundry authentication"):
        workflow_execution.execute_notebook_workflow(request, settings=_settings())
    database.close.assert_awaited_once()
