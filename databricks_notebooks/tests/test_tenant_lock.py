from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gds_workbench_notebooks.errors import (
    NotebookAuthorizationError,
    NotebookConfigurationError,
)
from gds_workbench_notebooks.tenant_lock import (
    TenantLockRequest,
    build_tenant_lock_request,
    create_tenant_lock_widgets,
    execute_tenant_lock_request,
    run_tenant_lock_notebook,
    tenant_lock_widget_specs,
)

_PASSWORD = "fixture-lock-password-must-stay-hidden"
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

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(
        self,
        statement: str,
        parameters: tuple[object, ...] | None = None,
    ) -> FakeCursor:
        self.calls.append((statement, parameters))
        return FakeCursor(self.rows.pop(0))


def _principal() -> dict[str, object]:
    return {
        "principal_display_name": "Databricks Notebook Runtime",
        "databricks_environment_code": "production",
    }


def _values(action: str = "check") -> dict[str, str]:
    return {
        "Action": action,
        "TenantID": "42",
        "Reason": "Manual notebook workflow",
        "DurationMinutes": "60",
    }


def _uploaded_root(tmp_path: Path) -> Path:
    root = tmp_path / "uploaded"
    root.mkdir()
    (root / ".env").write_text(
        f"""\
GDS_NOTEBOOK_POSTGRES_HOST=workbench.postgres.database.azure.com
GDS_NOTEBOOK_POSTGRES_PORT=5432
GDS_NOTEBOOK_POSTGRES_DATABASE=gds_workbench
GDS_NOTEBOOK_POSTGRES_USER=gds_notebook_runtime
GDS_NOTEBOOK_POSTGRES_PASSWORD={_PASSWORD}
GDS_NOTEBOOK_POSTGRES_SSLMODE=require
GDS_NOTEBOOK_POSTGRES_CONNECT_TIMEOUT_SECONDS=10
GDS_NOTEBOOK_POSTGRES_STATEMENT_TIMEOUT_SECONDS=30
"""
    )
    return root


def test_widget_contract_has_no_identity_model_or_force_override() -> None:
    specs = tenant_lock_widget_specs()

    assert tuple(spec.name for spec in specs) == (
        "Action",
        "TenantID",
        "Reason",
        "DurationMinutes",
    )
    assert specs[0].choices == ("check", "acquire", "renew", "release")
    assert not any(
        forbidden in spec.name.lower()
        for spec in specs
        for forbidden in ("principal", "identity", "model", "role", "force", "override")
    )


@pytest.mark.parametrize("action", ("check", "acquire", "renew", "release"))
def test_builds_each_explicit_lock_action(action: str) -> None:
    request = build_tenant_lock_request(_values(action))

    assert request.action == action
    assert request.tenant_id == 42
    assert request.reason == ("Manual notebook workflow" if action == "acquire" else None)
    assert request.duration_minutes == (60 if action in {"acquire", "renew"} else None)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("Action", "override"),
        ("TenantID", "0"),
        ("TenantID", "1 OR 1=1"),
        ("DurationMinutes", "241"),
        ("Reason", ""),
    ),
)
def test_rejects_invalid_lock_widget_input(field: str, value: str) -> None:
    values = _values("acquire")
    values[field] = value

    with pytest.raises(NotebookConfigurationError):
        build_tenant_lock_request(values)


@pytest.mark.parametrize(
    ("lock_request", "row", "function_name", "parameters", "succeeded"),
    (
        (
            TenantLockRequest("check", 42, None, None),
            {
                "authorized": True,
                "denial_code": None,
                "is_locked": False,
                "owner_display_name": None,
                "owned_by_current_principal": None,
                "purpose": None,
                "acquired_time": None,
                "expires_time": None,
            },
            "check_notebook_tenant_lock",
            (42,),
            True,
        ),
        (
            TenantLockRequest("acquire", 42, "Manual notebook workflow", 60),
            {
                "acquired": True,
                "denial_code": None,
                "owner_display_name": "Databricks Notebook Runtime",
                "purpose": "Manual notebook workflow",
                "acquired_time": _NOW,
                "expires_time": _NOW.replace(hour=13),
            },
            "acquire_notebook_tenant_lock",
            (42, 60, "Manual notebook workflow"),
            True,
        ),
        (
            TenantLockRequest("renew", 42, None, 30),
            {
                "renewed": True,
                "denial_code": None,
                "owner_display_name": "Databricks Notebook Runtime",
                "purpose": "Manual notebook workflow",
                "acquired_time": _NOW,
                "expires_time": _NOW.replace(minute=30),
            },
            "renew_notebook_tenant_lock",
            (42, 30),
            True,
        ),
        (
            TenantLockRequest("release", 42, None, None),
            {
                "released": True,
                "denial_code": None,
                "owner_display_name": "Databricks Notebook Runtime",
                "acquired_time": _NOW,
                "expires_time": _NOW.replace(hour=13),
            },
            "release_notebook_tenant_lock",
            (42,),
            True,
        ),
    ),
)
def test_calls_only_db_owned_identity_and_notebook_lock_wrappers(
    lock_request: TenantLockRequest,
    row: dict[str, object],
    function_name: str,
    parameters: tuple[object, ...],
    succeeded: bool,
) -> None:
    connection = FakeConnection(_principal(), row)

    result = execute_tenant_lock_request(connection, lock_request)

    assert result.succeeded is succeeded
    assert len(connection.calls) == 2
    assert "security.current_notebook_principal" in connection.calls[0][0]
    assert f"security.{function_name}" in connection.calls[1][0]
    assert connection.calls[0][1] is None
    assert connection.calls[1][1] == parameters


def test_unbound_database_login_fails_before_lock_operation() -> None:
    connection = FakeConnection(None)

    with pytest.raises(NotebookAuthorizationError, match="workload binding"):
        execute_tenant_lock_request(
            connection,
            TenantLockRequest("check", 42, None, None),
        )

    assert len(connection.calls) == 1
    assert "security.current_notebook_principal" in connection.calls[0][0]


def test_run_registers_widgets_and_prints_only_bounded_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeWidgets:
        def __init__(self) -> None:
            self.created: list[str] = []

        def dropdown(
            self,
            name: str,
            default: str,
            choices: list[str],
            label: str,
        ) -> None:
            self.created.append(name)

        def text(self, name: str, default: str, label: str) -> None:
            self.created.append(name)

        def get(self, name: str) -> str:
            return _values("check")[name]

    widgets = FakeWidgets()
    dbutils = type("Dbutils", (), {"widgets": widgets})()
    connection = FakeConnection(
        _principal(),
        {
            "authorized": True,
            "denial_code": None,
            "is_locked": False,
            "owner_display_name": None,
            "owned_by_current_principal": None,
            "purpose": None,
            "acquired_time": None,
            "expires_time": None,
        },
    )
    connector_calls: list[dict[str, object]] = []

    def connector(**kwargs: object) -> FakeConnection:
        connector_calls.append(kwargs)
        return connection

    create_tenant_lock_widgets(dbutils=dbutils)
    result = run_tenant_lock_notebook(
        dbutils=dbutils,
        uploaded_root=_uploaded_root(tmp_path),
        connector=connector,
    )

    output = capsys.readouterr().out
    assert result.as_dict() == {
        "action": "check",
        "tenant_id": 42,
        "succeeded": True,
        "is_locked": False,
    }
    assert output == '{"action":"check","is_locked":false,"succeeded":true,"tenant_id":42}\n'
    assert widgets.created == [spec.name for spec in tenant_lock_widget_specs()]
    assert _PASSWORD not in output
    assert connector_calls[0]["password"] == _PASSWORD


def test_tenant_lock_source_contains_only_the_governed_database_functions() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "gds_workbench_notebooks" / "tenant_lock.py"
    ).read_text()
    function_names = set(re.findall(r"security\.([a-z_]+)\(", source))

    assert function_names == {
        "current_notebook_principal",
        "check_notebook_tenant_lock",
        "acquire_notebook_tenant_lock",
        "renew_notebook_tenant_lock",
        "release_notebook_tenant_lock",
    }
    assert "override_tenant_lock" not in source
    assert "authorize_tenant_operation" not in source
