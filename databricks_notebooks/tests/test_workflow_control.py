from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from gds_workbench_notebooks.errors import (
    NotebookAuthorizationError,
    NotebookConfigurationError,
    NotebookDatabaseError,
)
from gds_workbench_notebooks.notebook import build_notebook_request, widget_specs
from gds_workbench_notebooks.workflow_control import (
    NotebookWorkflowControlClient,
    WorkflowClaimResult,
)

_CORRELATION_ID = UUID("12345678-1234-4234-8234-123456789abc")
_ACTOR_TENANT_ID = UUID("22345678-1234-4234-8234-123456789abc")
_ACTOR_OBJECT_ID = UUID("32345678-1234-4234-8234-123456789abc")
_CLAIM_TOKEN = UUID("42345678-1234-4234-8234-123456789abc")
_NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


class FakeCursor:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    def fetchone(self) -> dict[str, object] | None:
        return self._row


class FakeConnection:
    def __init__(self, *rows: dict[str, object] | None) -> None:
        self.rows = list(rows)
        self.calls: list[tuple[str, tuple[object, ...] | None]] = []

    def execute(
        self,
        statement: str,
        parameters: tuple[object, ...] | None = None,
    ) -> FakeCursor:
        self.calls.append((statement, parameters))
        return FakeCursor(self.rows.pop(0))


def _values(workflow: str) -> dict[str, str]:
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
    if workflow == "mapping":
        values.update(
            {
                "SelectedObjectIDsJSON": "[11]",
                "ExecutionMode": "tool_assisted",
                "MappingOperation": "extend",
                "MappingArtifactType": "python_notebook",
                "MappingSourceSystemID": "20",
                "MappingObjectOutputTemplateID": "21",
                "MappingAttributeOutputTemplateID": "22",
                "PromptOverridesJSON": '{"7":9}',
            }
        )
    elif workflow == "qa":
        values.update(
            {
                "SelectedObjectIDsJSON": "[]",
                "SelectedSystemCodesJSON": '["ERP","CRM"]',
            }
        )
    return values


def _create_row(*, created: bool = True, selected_scope_count: int = 2) -> dict[str, object]:
    return {
        "created": created,
        "denial_code": None,
        "workflow_run_id": 71,
        "workflow_run_state": "queued",
        "correlation_id": _CORRELATION_ID,
        "prompt_snapshot_count": 0,
        "created_time": _NOW,
        "model_revision": 4,
        "selected_scope_count": selected_scope_count,
        "code_generation_coverage_mode": None,
        "sql_generation_guide_version_id": None,
    }


def _claim_row() -> dict[str, object]:
    return {
        "workflow_run_id": 71,
        "tenant_id": 2,
        "model_id": 3,
        "model_revision": 4,
        "model_workflow": "profiling",
        "workflow_execution_mode": None,
        "correlation_id": _CORRELATION_ID,
        "actor_principal_type": "service_principal",
        "actor_entra_tenant_id": _ACTOR_TENANT_ID,
        "actor_entra_object_id": _ACTOR_OBJECT_ID,
        "workflow_run_claim_token": _CLAIM_TOKEN,
        "workflow_run_claimed_time": _NOW,
        "workflow_run_claim_expires_time": _NOW + timedelta(seconds=30),
        "workflow_run_recovery_count": 0,
    }


def _claim() -> WorkflowClaimResult:
    request = build_notebook_request("profiling", _values("profiling"))
    connection = FakeConnection(_create_row(), _claim_row())
    client = NotebookWorkflowControlClient(connection)
    created = client.create_workflow_run(request)
    claim = client.start_and_claim_workflow_run(
        request,
        created,
        lease_duration_seconds=30,
    )
    assert claim is not None
    return claim


def test_resolves_only_the_database_owned_notebook_principal() -> None:
    connection = FakeConnection(
        {
            "principal_display_name": "Databricks Notebook Runtime",
            "principal_type": "service_principal",
            "databricks_environment_code": "PROD",
            "entra_tenant_id": _ACTOR_TENANT_ID,
            "entra_object_id": _ACTOR_OBJECT_ID,
            "is_super_admin": True,
        }
    )

    principal = NotebookWorkflowControlClient(connection).current_principal()

    assert principal.display_name == "Databricks Notebook Runtime"
    assert principal.principal_type == "service_principal"
    assert principal.databricks_environment_code == "PROD"
    assert principal.entra_tenant_id == _ACTOR_TENANT_ID
    assert principal.entra_object_id == _ACTOR_OBJECT_ID
    assert str(_ACTOR_TENANT_ID) not in repr(principal)
    assert str(_ACTOR_OBJECT_ID) not in repr(principal)
    assert "security.current_notebook_principal()" in connection.calls[0][0]
    assert connection.calls[0][1] is None


def test_unbound_login_fails_before_any_workflow_control() -> None:
    connection = FakeConnection(None)

    with pytest.raises(NotebookAuthorizationError, match="workload binding"):
        NotebookWorkflowControlClient(connection).current_principal()

    assert len(connection.calls) == 1


def test_create_uses_exact_actor_free_wrapper_parameters() -> None:
    request = build_notebook_request("mapping", _values("mapping"))
    row = _create_row(selected_scope_count=1)
    row["prompt_snapshot_count"] = 6
    connection = FakeConnection(row)

    result = NotebookWorkflowControlClient(connection).create_workflow_run(request)

    statement, parameters = connection.calls[0]
    assert "application.create_notebook_workflow_run(" in statement
    assert parameters == (
        2,
        3,
        4,
        "mapping",
        "tool_assisted",
        "langchain_create_agent",
        "databricks",
        "databricks-primary",
        "default",
        10,
        2,
        [11],
        [],
        None,
        None,
        _CORRELATION_ID,
        '{"7":9}',
        "extend",
        "selected_targets",
        "python_notebook",
        20,
        21,
        22,
        None,
        None,
    )
    assert result.workflow_run_id == 71
    assert result.workflow == "mapping"
    assert result.prompt_snapshot_count == 6


def test_qa_create_passes_system_codes_immediately_after_empty_object_ids() -> None:
    request = build_notebook_request("qa", _values("qa"))
    connection = FakeConnection(_create_row(selected_scope_count=2))

    result = NotebookWorkflowControlClient(connection).create_workflow_run(request)

    statement, parameters = connection.calls[0]
    assert "%s::BIGINT[],\n                  %s::VARCHAR[]" in statement
    assert parameters is not None
    assert parameters[4] is None
    assert parameters[11:13] == ([], ["ERP", "CRM"])
    assert result.workflow == "qa"
    assert result.selected_scope_count == 2


def test_create_replay_preserves_idempotency_key_and_run_id() -> None:
    request = build_notebook_request("profiling", _values("profiling"))
    connection = FakeConnection(_create_row(), _create_row(created=False))
    client = NotebookWorkflowControlClient(connection)

    created = client.create_workflow_run(request)
    replayed = client.create_workflow_run(request)

    assert created.created is True
    assert replayed.created is False
    assert replayed.workflow_run_id == created.workflow_run_id
    assert replayed.correlation_id == request.idempotency_key
    assert connection.calls[0][1] == connection.calls[1][1]
    assert connection.calls[0][1] is not None
    assert connection.calls[0][1][15] == _CORRELATION_ID


def test_start_claim_renew_and_release_use_exact_wrapper_parameters() -> None:
    request = build_notebook_request("profiling", _values("profiling"))
    connection = FakeConnection(
        _create_row(),
        _claim_row(),
        {
            "workflow_run_id": 71,
            "workflow_run_claim_heartbeat_time": _NOW + timedelta(seconds=10),
            "workflow_run_claim_expires_time": _NOW + timedelta(seconds=40),
        },
        {"released": True},
    )
    client = NotebookWorkflowControlClient(connection)
    created = client.create_workflow_run(request)

    claim = client.start_and_claim_workflow_run(
        request,
        created,
        lease_duration_seconds=30,
    )
    assert claim is not None
    renewed = client.renew_workflow_run_claim(claim, lease_duration_seconds=30)
    released = client.release_workflow_run_claim(claim)

    assert "start_and_claim_notebook_workflow_run(" in connection.calls[1][0]
    assert connection.calls[1][1] == (2, 3, 71, 4, "profiling", 30)
    assert "renew_notebook_workflow_run_claim(" in connection.calls[2][0]
    assert connection.calls[2][1] == (71, _CLAIM_TOKEN, 30)
    assert "release_notebook_workflow_run_claim(" in connection.calls[3][0]
    assert connection.calls[3][1] == (71, _CLAIM_TOKEN)
    assert renewed.workflow_run_id == 71
    assert renewed.succeeded is True
    assert renewed.heartbeat_time == _NOW + timedelta(seconds=10)
    assert renewed.expires_time == _NOW + timedelta(seconds=40)
    assert released.workflow_run_id == 71
    assert released.succeeded is True
    assert released.heartbeat_time is None
    assert released.expires_time is None


def test_start_claim_returns_no_claim_without_masking_the_database_outcome() -> None:
    request = build_notebook_request("profiling", _values("profiling"))
    connection = FakeConnection(_create_row(), None)
    client = NotebookWorkflowControlClient(connection)
    created = client.create_workflow_run(request)

    claim = client.start_and_claim_workflow_run(
        request,
        created,
        lease_duration_seconds=30,
    )

    assert claim is None


def test_claim_token_is_available_to_execution_but_never_rendered() -> None:
    claim = _claim()

    assert claim.claim_token == _CLAIM_TOKEN
    assert str(_CLAIM_TOKEN) not in repr(claim)


def test_public_control_methods_accept_no_actor_identity_input() -> None:
    signatures = {
        name: inspect.signature(getattr(NotebookWorkflowControlClient, name))
        for name in (
            "current_principal",
            "create_workflow_run",
            "start_and_claim_workflow_run",
            "renew_workflow_run_claim",
            "release_workflow_run_claim",
        )
    }

    assert all(
        not any(
            actor_field in parameter.lower()
            for parameter in signature.parameters
            for actor_field in ("actor", "principal", "entra", "identity")
        )
        for signature in signatures.values()
    )


def test_control_source_calls_only_governed_notebook_wrappers() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "gds_workbench_notebooks" / "workflow_control.py"
    ).read_text()
    function_names = set(re.findall(r"(?:security|application)\.([a-z_]+)\(", source))

    assert function_names == {
        "current_notebook_principal",
        "create_notebook_workflow_run",
        "start_and_claim_notebook_workflow_run",
        "renew_notebook_workflow_run_claim",
        "release_notebook_workflow_run_claim",
    }
    assert "actor_entra" not in "\n".join(line for line in source.splitlines() if "%s::" in line)


def test_driver_error_is_bounded_and_does_not_disclose_raw_text() -> None:
    class FailingConnection:
        def execute(self, statement: str, parameters: object = None) -> None:
            raise RuntimeError("raw-row fixture-password fixture-token")

    request = build_notebook_request("profiling", _values("profiling"))

    with pytest.raises(NotebookDatabaseError) as captured:
        NotebookWorkflowControlClient(FailingConnection()).create_workflow_run(request)

    assert "raw-row" not in str(captured.value)
    assert "fixture-password" not in str(captured.value)
    assert "fixture-token" not in str(captured.value)


def test_create_reports_missing_prompt_assignment_without_raw_database_details() -> None:
    class Diagnostic:
        message_primary = "No usable prompt is assigned to Workflow Stage 31"

    class MissingPromptError(RuntimeError):
        diag = Diagnostic()

    class FailingConnection:
        def execute(self, statement: str, parameters: object = None) -> None:
            raise MissingPromptError("raw-row fixture-password fixture-token")

    request = build_notebook_request("analysis_inference", _values("analysis_inference"))

    with pytest.raises(
        NotebookConfigurationError,
        match="active published prompt",
    ) as captured:
        NotebookWorkflowControlClient(FailingConnection()).create_workflow_run(request)

    assert "Workflow Stage 31" not in str(captured.value)
    assert "fixture-password" not in str(captured.value)
    assert "fixture-token" not in str(captured.value)
