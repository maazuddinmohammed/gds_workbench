from __future__ import annotations

import subprocess
import sys
import zipfile

# pyright: reportPrivateUsage=false
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from psycopg import AsyncConnection
from psycopg.errors import InsufficientPrivilege

import gds_etl_workbench.diagnostics.metadata_snapshot as diagnostic_module
from gds_etl_workbench.configuration import RuntimeSettings
from gds_etl_workbench.diagnostics.metadata_snapshot import (
    _failure_fields,
    _run_database_diagnostic,
    _TracingReadTransaction,
    inspect_deployment,
    load_settings_for_diagnostic,
)
from gds_etl_workbench.tools.snapshots.metadata.sql import (
    OBJECT_CLOSURE_SQL,
    OBJECT_ROWS_SQL,
)

BUILD_SCRIPT = Path(__file__).parents[2] / "mcp_server" / "build_zip.py"


class _Result:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self._row = row
        self._rows = rows or []

    async def fetchone(self) -> dict[str, Any] | None:
        return self._row

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


def _local_settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_ENVIRONMENT": "local",
            "GDS_DATABASE_DSN": "postgresql://runtime.invalid/workbench",
            "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_LOCAL_PRINCIPAL_OBJECT_ID": "33333333-3333-3333-3333-333333333333",
            "GDS_MCP_PUBLIC_URL": "http://localhost:8000/mcp",
            "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": (
                "https://snapshot.blob.core.windows.net"
            ),
            "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
        }
    )


class _FakePool:
    connection_instance: Any

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.connection_instance = _RoleFailureConnection()

    async def open(self, *, wait: bool) -> None:
        assert wait is False

    async def close(self) -> None:
        return None

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[Any]:
        yield self.connection_instance


class _RoleFailureConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        yield

    async def execute(self, query: object, _parameters: object = ()) -> _Result:
        sql = str(query)
        self.executed.append(sql)
        if sql == diagnostic_module._LOGIN_POSTURE_SQL:
            return _Result(
                row={
                    "expected_login": True,
                    "role_exists": True,
                    "is_member": True,
                    "can_set_role": True,
                    "exact_membership": True,
                }
            )
        if sql == "SET LOCAL ROLE gds_app_write":
            raise InsufficientPrivilege("SENTINEL_ROLE_FAILURE")
        return _Result()


class _SelectionFailurePool(_FakePool):
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.connection_instance = _SelectionFailureConnection()


class _QueryFailureConnection:
    async def execute(self, _query: object, _parameters: object = ()) -> _Result:
        raise InsufficientPrivilege("SENTINEL_QUERY_FAILURE")


class _SelectionFailureConnection(_RoleFailureConnection):
    async def execute(self, query: object, _parameters: object = ()) -> _Result:
        sql = str(query)
        self.executed.append(sql)
        if sql == diagnostic_module._LOGIN_POSTURE_SQL:
            return _Result(
                row={
                    "expected_login": True,
                    "role_exists": True,
                    "is_member": True,
                    "can_set_role": True,
                    "exact_membership": True,
                }
            )
        if sql == diagnostic_module._READINESS_BOOTSTRAP_SQL:
            return _Result(row={"postgres_major": 18, "contract_exists": True})
        if sql == diagnostic_module._READINESS_SQL:
            return _Result(
                row={
                    "schema_version": "1.0.0",
                    "postgres_major": 18,
                    "schema_shape_ok": True,
                    "runtime_role_ok": True,
                    "runtime_privileges_ok": True,
                    "runtime_query_contract_ok": True,
                }
            )
        if sql == diagnostic_module._TRANSACTION_POSTURE_SQL:
            return _Result(
                row={
                    "expected_login": True,
                    "active_role": True,
                    "local_role": True,
                    "repeatable_read": True,
                    "read_only": True,
                }
            )
        if sql == diagnostic_module._SCHEMA_ACL_SQL:
            return _Result(
                rows=[
                    {
                        "schema_name": name,
                        "schema_exists": True,
                        "can_use": name != "model",
                    }
                    for name in diagnostic_module._REQUIRED_SCHEMAS
                ]
            )
        if sql == diagnostic_module._RELATION_ACL_SQL:
            return _Result(
                rows=[
                    {
                        "relation_name": name,
                        "relation_exists": True,
                        "can_select": name != "model.model_scope",
                    }
                    for name in diagnostic_module._SNAPSHOT_RELATIONS
                ]
            )
        if sql == OBJECT_CLOSURE_SQL:
            raise InsufficientPrivilege("SENTINEL_QUERY_AND_ROW_DATA")
        return _Result()


def test_database_failure_fields_never_emit_raw_database_detail() -> None:
    fields = _failure_fields(InsufficientPrivilege("SENTINEL_DSN_QUERY_AND_ROW"))

    assert fields == "type=InsufficientPrivilege sqlstate=42501"
    assert "SENTINEL" not in fields


@pytest.mark.asyncio
async def test_selection_tracer_retains_only_the_fixed_query_stage() -> None:
    connection = _QueryFailureConnection()
    transaction = _TracingReadTransaction(cast(AsyncConnection[Any], connection))

    with pytest.raises(InsufficientPrivilege):
        await transaction.fetch_all(OBJECT_ROWS_SQL)

    assert transaction.last_stage == "object_rows"


@pytest.mark.asyncio
async def test_local_diagnostic_still_requires_transaction_role_activation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(diagnostic_module, "AsyncConnectionPool", _FakePool)

    result = await _run_database_diagnostic(_local_settings(), tenant_id=5)

    assert result.succeeded is False
    assert result.selected is None
    output = capsys.readouterr().out
    assert output.count("stage=role_activation") == 2
    assert "sqlstate=42501" in output
    assert "SENTINEL_ROLE_FAILURE" not in output


@pytest.mark.asyncio
async def test_diagnostic_identifies_acl_and_exact_selection_stage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(diagnostic_module, "AsyncConnectionPool", _SelectionFailurePool)

    result = await _run_database_diagnostic(_local_settings(), tenant_id=5)

    assert result.succeeded is False
    assert result.selected is None
    output = capsys.readouterr().out
    assert "database=OK code=ready" in output
    assert "transaction_posture=OK" in output
    assert "snapshot_acl=FAILED" in output
    assert "schema_usage_missing=model" in output
    assert "select_missing=model.model_scope" in output
    assert "selection=FAILED stage=object_closure" in output
    assert "sqlstate=42501" in output
    assert "SENTINEL_QUERY_AND_ROW_DATA" not in output


def test_configuration_diagnostic_recovers_without_mutating_production_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = {
        "GDS_ENVIRONMENT": "production",
        "GDS_DATABASE_DSN": (
            "postgresql://app@db.example.invalid/workbench?sslmode=verify-full"
        ),
        "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
        "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
        "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
        "GDS_LOCAL_PRINCIPAL_OBJECT_ID": "33333333-3333-3333-3333-333333333333",
        "GDS_MCP_PUBLIC_URL": "https://workbench.example.test/mcp",
        "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": (
            "https://snapshot.blob.core.windows.net"
        ),
        "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
    }

    settings, clean = load_settings_for_diagnostic(values)

    assert settings is not None
    assert clean is False
    assert "GDS_LOCAL_PRINCIPAL_OBJECT_ID" in values
    output = capsys.readouterr().out
    assert "configuration=FAILED" in output
    assert "configuration_recovery=OK" in output


def test_deployment_inspection_checks_every_manifest_file(tmp_path: Path) -> None:
    artifact = tmp_path / "app.zip"
    completed = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), "--output", str(artifact)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0

    deployed_root = tmp_path / "deployed"
    with zipfile.ZipFile(artifact) as archive:
        archive.extractall(deployed_root)

    inspection = inspect_deployment(deployed_root)
    assert inspection.status == "OK"
    assert inspection.file_count > 0
    assert inspection.missing_count == 0
    assert inspection.mismatch_count == 0
    assert inspection.configuration_matches is True
    assert inspection.metadata_snapshot_matches is True

    help_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gds_etl_workbench.diagnostics.metadata_snapshot",
            "--help",
        ],
        cwd=deployed_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "--tenant-id" in help_result.stdout

    diagnostic_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gds_etl_workbench.diagnostics.metadata_snapshot",
            "--tenant-id",
            "5",
        ],
        cwd=deployed_root,
        env={},
        check=False,
        capture_output=True,
        text=True,
    )
    assert diagnostic_result.returncode == 1
    assert "deployment=OK" in diagnostic_result.stdout
    assert "configuration_source=OK" in diagnostic_result.stdout
    assert "metadata_snapshot_source=OK" in diagnostic_result.stdout
    assert "configuration=FAILED" in diagnostic_result.stdout
    assert "diagnostic=FAILED" in diagnostic_result.stdout
    assert diagnostic_result.stderr == ""

    configuration = deployed_root / "gds_etl_workbench" / "configuration.py"
    configuration.write_bytes(configuration.read_bytes() + b"\n# stale deployment\n")
    (deployed_root / "gds_etl_workbench" / "stale_file.py").write_text("pass\n")

    stale = inspect_deployment(deployed_root)
    assert stale.status == "FAILED"
    assert stale.missing_count == 0
    assert stale.mismatch_count == 1
    assert stale.unlisted_python_count == 1
    assert stale.configuration_matches is False
    assert stale.metadata_snapshot_matches is True
