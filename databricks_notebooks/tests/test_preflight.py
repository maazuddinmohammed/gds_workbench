from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import pytest
from gds_workbench_notebooks import (
    NotebookConfigurationError,
    NotebookDatabaseSettings,
    NotebookPreflightResult,
    NotebookRuntimeSettings,
    execute_notebook_preflight,
    preflight,
)

_TENANT_ID = UUID("22345678-1234-4234-8234-123456789abc")
_OBJECT_ID = UUID("32345678-1234-4234-8234-123456789abc")


def _settings(*, endpoint: str | None = "gds-primary") -> NotebookRuntimeSettings:
    return NotebookRuntimeSettings(
        database=NotebookDatabaseSettings(
            host="workbench.postgres.database.azure.com",
            port=5432,
            database="gds_workbench",
            user="gds_notebook_runtime",
            password="fixture-preflight-password",
        ),
        databricks_model_endpoint=endpoint,
    )


def test_preflight_checks_fixed_identity_then_async_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    @contextmanager
    def connection(_settings):
        yield object()

    class Client:
        def __init__(self, _connection) -> None:
            pass

        def current_principal(self):
            calls.append("identity")
            from gds_workbench_notebooks import NotebookPrincipal

            return NotebookPrincipal(
                display_name="Databricks Notebook Runtime",
                principal_type="service_principal",
                databricks_environment_code="PROD",
                entra_tenant_id=_TENANT_ID,
                entra_object_id=_OBJECT_ID,
            )

    async def check(settings, principal):
        calls.append("runtime")
        assert settings.databricks_model_endpoint == "gds-primary"
        return NotebookPreflightResult(
            python_version="3.12",
            database_ready=True,
            shared_runtime_ready=True,
            unified_auth_ready=True,
            principal_display_name=principal.display_name,
            principal_type=principal.principal_type,
            databricks_environment_code=principal.databricks_environment_code,
        )

    monkeypatch.setattr(preflight, "notebook_database_connection", connection)
    monkeypatch.setattr(preflight, "NotebookWorkflowControlClient", Client)

    result = execute_notebook_preflight(
        _settings(),
        python_version=(3, 12),
        async_check=check,
    )

    assert calls == ["identity", "runtime"]
    assert result.as_dict() == {
        "python_version": "3.12",
        "database_ready": True,
        "shared_runtime_ready": True,
        "unified_auth_ready": True,
        "principal_display_name": "Databricks Notebook Runtime",
        "principal_type": "service_principal",
        "databricks_environment_code": "PROD",
    }


@pytest.mark.parametrize("python_version", ((3, 11), (3, 13), (3, 14)))
def test_preflight_requires_dbr_16_4_python_image(python_version: tuple[int, int]) -> None:
    with pytest.raises(NotebookConfigurationError, match="Python 3.12"):
        execute_notebook_preflight(_settings(), python_version=python_version)


def test_preflight_requires_endpoint_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preflight,
        "notebook_database_connection",
        lambda _settings: pytest.fail("database must not be opened"),
    )

    with pytest.raises(NotebookConfigurationError, match="MODEL_ENDPOINT"):
        execute_notebook_preflight(
            _settings(endpoint=None),
            python_version=(3, 12),
        )


def test_preflight_notebook_is_source_only_and_starts_no_server() -> None:
    root = Path(__file__).parents[1]
    source = (root / "notebooks" / "01_runtime_preflight.py").read_text()

    assert source.startswith("# Databricks notebook source\n")
    assert 'str(_UPLOAD_ROOT / "src")' in source
    assert "run_notebook_preflight(" in source
    assert "FastAPI(" not in source
    assert "MCPServer(" not in source
