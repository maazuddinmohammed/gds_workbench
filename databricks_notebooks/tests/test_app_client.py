import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from gds_workbench_notebooks import (
    DatabricksAppApiClient,
    NotebookApiError,
    NotebookConfigurationError,
    NotebookTenantWorkflowConflictError,
)

_IDEMPOTENCY_KEY = UUID("12345678-1234-4234-8234-123456789abc")


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._raw = json.dumps(payload).encode()
        self.closed = False

    def iter_content(self, *, chunk_size: int):
        assert chunk_size == 64 * 1024
        yield self._raw

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def _dbutils(token: str = "fixture-notebook-token") -> object:
    token_value = SimpleNamespace(get=lambda: token)
    context = SimpleNamespace(apiToken=lambda: token_value)
    notebook = SimpleNamespace(getContext=lambda: context)
    internal_dbutils = SimpleNamespace(notebook=lambda: notebook)
    entry_point = SimpleNamespace(getDbutils=lambda: internal_dbutils)
    return SimpleNamespace(notebook=SimpleNamespace(entry_point=entry_point))


def _workspace(
    *,
    app_url: str = "https://workbench-123.eastus.databricksapps.com",
) -> object:
    app = SimpleNamespace(url=app_url, oauth2_app_client_id="fixture-app-client-id")
    return SimpleNamespace(
        apps=SimpleNamespace(get=lambda name: app),
        config=SimpleNamespace(host="https://adb-123.4.azuredatabricks.net"),
    )


def _client(session: FakeSession, **kwargs: object) -> DatabricksAppApiClient:
    return DatabricksAppApiClient.from_notebook(
        app_name="gds-workbench",
        dbutils=_dbutils(),
        workspace_client=_workspace(),
        session=session,
        **kwargs,
    )


def test_exchanges_notebook_token_and_calls_app_as_notebook_user() -> None:
    responses = (
        FakeResponse(200, {"access_token": "fixture-audience-token"}),
        FakeResponse(201, {"created": True, "workflow_run_id": 71}),
        FakeResponse(202, {"workflow_run_state": "running"}),
        FakeResponse(
            200,
            {
                "workflow_run_state": "completed",
                "failure_code": None,
                "failure_message": None,
            },
        ),
    )
    session = FakeSession(*responses)
    sleeps: list[float] = []
    client = _client(session, sleep=sleeps.append, monotonic=lambda: 0.0)

    result = client.launch_workflow(
        tenant_id=2,
        model_id=3,
        workflow="profiling",
        analysis_operation=None,
        expected_model_revision=4,
        idempotency_key=_IDEMPOTENCY_KEY,
        create_payload={"workflow_execution_mode": None},
        wait_timeout_seconds=10,
    )

    exchange, create, execute, poll = session.calls
    assert exchange["url"] == "https://adb-123.4.azuredatabricks.net/oidc/v1/token"
    assert exchange["data"] == {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": "fixture-notebook-token",
        "subject_token_type": "urn:databricks:params:oauth:token-type:personal-access-token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "scope": "all-apis",
        "audience": "fixture-app-client-id",
    }
    assert "Authorization" not in exchange["headers"]
    assert create["url"].endswith("/api/v1/tenants/2/models/3/runs")
    assert create["headers"]["Authorization"] == "Bearer fixture-audience-token"
    assert create["headers"]["Idempotency-Key"] == str(_IDEMPOTENCY_KEY)
    assert execute["url"].endswith("/profiling/runs/71/execute")
    assert execute["json"] == {"expected_model_revision": 4}
    assert poll["url"].endswith("/runs/71")
    assert all(call["allow_redirects"] is False for call in session.calls)
    assert all(call["stream"] is True for call in session.calls)
    assert all(response.closed for response in responses)
    assert sleeps == [2.0]
    assert result.as_dict() == {
        "workflow_run_id": 71,
        "workflow": "profiling",
        "state": "completed",
        "created": True,
    }
    assert "fixture-notebook-token" not in repr(client)
    assert "fixture-audience-token" not in repr(client)


@pytest.mark.parametrize(
    ("workflow", "analysis_operation", "route", "execution_mode"),
    (
        ("profiling", None, "profiling/runs", None),
        ("analysis", "inference", "analysis/inference-runs", "one_shot"),
        ("analysis", "validation", "analysis/validation-runs", None),
        ("conceptual", None, "conceptual/runs", "one_shot"),
        ("logical", None, "logical/runs", "tool_assisted"),
        ("dimensional", None, "dimensional/runs", "detailed_coverage"),
        ("mapping", None, "mapping/runs", "one_shot"),
        ("code_generation", None, "code-generation/runs", None),
    ),
)
def test_uses_exact_existing_execution_route(
    workflow: str,
    analysis_operation: str | None,
    route: str,
    execution_mode: str | None,
) -> None:
    session = FakeSession(
        FakeResponse(200, {"access_token": "fixture-audience-token"}),
        FakeResponse(201, {"created": True, "workflow_run_id": 91}),
        FakeResponse(202, {"workflow_run_state": "running"}),
    )
    client = _client(session)

    result = client.launch_workflow(
        tenant_id=2,
        model_id=3,
        workflow=workflow,
        analysis_operation=analysis_operation,
        expected_model_revision=4,
        idempotency_key=_IDEMPOTENCY_KEY,
        create_payload={"workflow_execution_mode": execution_mode},
        wait_timeout_seconds=0,
    )

    execute = session.calls[2]
    assert execute["url"].endswith(f"/{route}/91/execute")
    expected: dict[str, object] = {"expected_model_revision": 4}
    if workflow in {"conceptual", "logical", "dimensional", "mapping"}:
        expected["execution_mode"] = execution_mode
    assert execute["json"] == expected
    assert result.workflow == (
        f"analysis_{analysis_operation}" if workflow == "analysis" else workflow
    )


def test_tenant_conflict_preserves_created_queued_run_and_gives_retry_instruction() -> None:
    session = FakeSession(
        FakeResponse(200, {"access_token": "fixture-audience-token"}),
        FakeResponse(201, {"created": True, "workflow_run_id": 73}),
        FakeResponse(
            409,
            {
                "error": {
                    "code": "tenant_workflow_conflict",
                    "message": "Another Workflow Run is already active for this Tenant.",
                    "correlation_id": "98765432-1234-4234-8234-123456789abc",
                }
            },
        ),
    )

    with pytest.raises(NotebookTenantWorkflowConflictError) as captured:
        _client(session).launch_workflow(
            tenant_id=2,
            model_id=3,
            workflow="profiling",
            analysis_operation=None,
            expected_model_revision=4,
            idempotency_key=_IDEMPOTENCY_KEY,
            create_payload={"workflow_execution_mode": None},
            wait_timeout_seconds=0,
        )

    assert captured.value.workflow_run_id == 73
    assert captured.value.correlation_id == "98765432-1234-4234-8234-123456789abc"
    assert "remains queued" in str(captured.value)
    assert "same IdempotencyKey" in str(captured.value)
    assert "fixture-audience-token" not in str(captured.value)


def test_refreshes_audience_token_once_after_unauthorized_response() -> None:
    session = FakeSession(
        FakeResponse(200, {"access_token": "fixture-audience-token-one"}),
        FakeResponse(401, {"error": {"code": "authentication_failed"}}),
        FakeResponse(200, {"access_token": "fixture-audience-token-two"}),
        FakeResponse(201, {"created": True, "workflow_run_id": 80}),
        FakeResponse(202, {"workflow_run_state": "running"}),
    )

    result = _client(session).launch_workflow(
        tenant_id=2,
        model_id=3,
        workflow="profiling",
        analysis_operation=None,
        expected_model_revision=4,
        idempotency_key=_IDEMPOTENCY_KEY,
        create_payload={"workflow_execution_mode": None},
        wait_timeout_seconds=0,
    )

    exchange_calls = [call for call in session.calls if str(call["url"]).endswith("oidc/v1/token")]
    assert len(exchange_calls) == 2
    assert session.calls[3]["headers"]["Authorization"] == "Bearer fixture-audience-token-two"
    assert result.state == "running"


def test_wait_polling_backs_off_and_stays_bounded() -> None:
    session = FakeSession(
        FakeResponse(200, {"access_token": "fixture-audience-token"}),
        FakeResponse(201, {"created": True, "workflow_run_id": 81}),
        FakeResponse(202, {"workflow_run_state": "running"}),
        *(FakeResponse(200, {"workflow_run_state": "running"}) for _ in range(5)),
        FakeResponse(200, {"workflow_run_state": "completed"}),
    )
    sleeps: list[float] = []

    result = _client(session, sleep=sleeps.append, monotonic=lambda: 0.0).launch_workflow(
        tenant_id=2,
        model_id=3,
        workflow="profiling",
        analysis_operation=None,
        expected_model_revision=4,
        idempotency_key=_IDEMPOTENCY_KEY,
        create_payload={"workflow_execution_mode": None},
        wait_timeout_seconds=300,
    )

    assert result.state == "completed"
    assert sleeps == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


def test_rejects_non_databricks_app_url_before_any_http_request() -> None:
    session = FakeSession()
    with pytest.raises(NotebookConfigurationError, match="not a Databricks Apps URL"):
        DatabricksAppApiClient.from_notebook(
            app_name="gds-workbench",
            dbutils=_dbutils(),
            workspace_client=_workspace(app_url="https://example.com"),
            session=session,
        )
    assert session.calls == []


def test_transport_failure_does_not_disclose_exception_or_tokens() -> None:
    class FailingSession:
        def request(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("fixture-notebook-token must not escape")

    client = _client(FailingSession())
    with pytest.raises(NotebookApiError) as captured:
        client.launch_workflow(
            tenant_id=2,
            model_id=3,
            workflow="profiling",
            analysis_operation=None,
            expected_model_revision=4,
            idempotency_key=_IDEMPOTENCY_KEY,
            create_payload={"workflow_execution_mode": None},
            wait_timeout_seconds=0,
        )
    assert "fixture-notebook-token" not in str(captured.value)
