"""Safe, authenticated observations of the actual embedded worker."""

# pyright: reportPrivateUsage=false

import ast
import asyncio
import hashlib
import json
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from gds_workbench_api import runtime_diagnostics as diagnostics_module
from gds_workbench_api.authentication import WebIdentityProvider
from gds_workbench_api.features.workflows.execution import WorkflowExecutionWorker
from gds_workbench_api.main import create_app
from gds_workbench_api.runtime import create_runtime_app
from gds_workbench_api.runtime_diagnostics import (
    RuntimeDiagnostics,
    source_tree_sha256,
)
from gds_workbench_api.workflow_worker import create_worker_runtime
from psycopg.errors import InsufficientPrivilege
from test_runtime_wiring import LifecycleDatabase
from test_workflow_execution_worker import BlockingDispatcher, FakeClaimRepository
from test_workflow_worker_runtime import _settings

ENDPOINT = "/api/v1/config/runtime-diagnostics"


def test_fingerprint_helper_preserves_standalone_builder_python_syntax() -> None:
    assert diagnostics_module.__file__ is not None
    ast.parse(Path(diagnostics_module.__file__).read_text(), feature_version=(3, 10))


def test_source_fingerprint_uses_relative_source_bytes_and_ignores_bytecode(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/options.json").write_bytes(b'{"enabled":true}')
    (tmp_path / "worker.py").write_bytes(b"version = 1\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__/worker.py").write_bytes(b"ignored")
    (tmp_path / "worker.pyc").write_bytes(b"ignored")
    expected = hashlib.sha256()
    for relative in ("config/options.json", "worker.py"):
        expected.update(relative.encode() + b"\0")
        expected.update(hashlib.sha256((tmp_path / relative).read_bytes()).digest())
    initial = source_tree_sha256(tmp_path)
    assert initial == expected.hexdigest()
    (tmp_path / "worker.py").write_bytes(b"version = 2\n")
    source_changed = source_tree_sha256(tmp_path)
    assert source_changed != initial
    (tmp_path / "config/options.json").write_bytes(b'{"enabled":false}')
    assert source_tree_sha256(tmp_path) != source_changed


def test_source_fingerprint_rejects_missing_empty_and_linked_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        source_tree_sha256(tmp_path / "missing")
    with pytest.raises(ValueError):
        source_tree_sha256(tmp_path)
    (tmp_path / "source.py").write_bytes(b"pass\n")
    (tmp_path / "alias.py").symlink_to(tmp_path / "source.py")
    with pytest.raises(ValueError):
        source_tree_sha256(tmp_path)


def test_installed_fingerprints_capture_once_and_snapshot_is_immutable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics = RuntimeDiagnostics.capture_installed_sources()
    original = diagnostics.snapshot()
    assert original.installed_source.api_sha256 is not None
    assert original.installed_source.shared_sha256 is not None
    assert len(original.installed_source.api_sha256) == 64
    assert len(original.installed_source.shared_sha256) == 64

    def forbid_disk_read(_path: Path) -> bytes:
        raise AssertionError("requests must not read source files")

    monkeypatch.setattr(Path, "read_bytes", forbid_disk_read)
    assert diagnostics.snapshot() == original
    with pytest.raises(FrozenInstanceError):
        original.worker.state = "polling"  # pyright: ignore[reportAttributeAccessIssue]


def test_missing_fingerprint_is_bounded_and_does_not_stop_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreadable(_path: Path) -> bytes:
        raise PermissionError("synthetic-private-path")

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    snapshot = RuntimeDiagnostics.capture_installed_sources().snapshot()
    assert snapshot.installed_source.api_sha256 is None
    assert snapshot.installed_source.shared_sha256 is None
    assert "synthetic-private-path" not in json.dumps(asdict(snapshot))


def test_runtime_diagnostics_require_authentication_and_leave_health_public() -> None:
    app = create_app(
        identity_provider=WebIdentityProvider(), runtime_diagnostics=RuntimeDiagnostics()
    )
    with TestClient(app) as client:
        response = client.get(ENDPOINT)
        assert response.status_code == 401
        assert "installed_source" not in response.text
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.post(ENDPOINT).status_code == 405
    with TestClient(create_app(runtime_diagnostics=RuntimeDiagnostics())) as client:
        assert client.get(ENDPOINT).status_code == 404


def test_runtime_endpoint_observes_same_diagnostics_as_assembled_worker() -> None:
    diagnostics = RuntimeDiagnostics()
    app = create_runtime_app(
        settings=_settings(), database=LifecycleDatabase(), diagnostics=diagnostics
    )
    with TestClient(app, base_url="http://localhost:8000") as client:
        before = client.get(ENDPOINT)
        assert before.status_code == 200
        assert before.headers["Cache-Control"] == "no-store"
        assert before.json()["worker"]["state"] == "not_attached"

        worker = create_worker_runtime(
            settings=_settings(), database=LifecycleDatabase(), diagnostics=diagnostics
        )
        assert worker.diagnostics is diagnostics
        private_error = InsufficientPrivilege("synthetic-private-claim-error")
        worker.worker._claims = AsyncMock(claim_next=AsyncMock(side_effect=private_error))
        try:
            with pytest.raises(InsufficientPrivilege):
                asyncio.run(worker.worker.run_once())
            after = client.get(ENDPOINT)
            payload = after.json()
            assert payload["worker"]["last_poll_result"] == "poll_failed"
            assert payload["worker"]["last_fault"]["category"] == "database_access"
            assert payload["worker"]["last_fault"]["boundary"] == "claim"
            assert "synthetic-private-claim-error" not in after.text
            assert set(payload) == {"installed_source", "worker"}
            assert payload["worker"]["active_runs"] == 0
            assert set(payload["worker"]) == {
                "state",
                "started",
                "active_runs",
                "readiness_code",
                "boundary",
                "last_poll_result",
                "last_poll_age_seconds",
                "last_fault",
            }
            assert set(payload["worker"]["last_fault"]) == {"category", "boundary", "age_seconds"}
        finally:
            asyncio.run(worker.services.close())


@pytest.mark.asyncio
async def test_claim_failure_has_bounded_category_and_retains_original_exception() -> None:
    clock = [10.0]
    diagnostics = RuntimeDiagnostics(clock=lambda: clock[0])
    private_error = InsufficientPrivilege("synthetic-private-claim-error")

    class FailingClaims(FakeClaimRepository):
        async def claim_next(self, **_kwargs: Any) -> None:
            raise private_error

    worker = WorkflowExecutionWorker(
        claims=FailingClaims(None),
        dispatcher=BlockingDispatcher(),
        lease_duration_seconds=30,
        heartbeat_interval_seconds=10,
        diagnostics=diagnostics,
    )
    with pytest.raises(InsufficientPrivilege) as caught:
        await worker.run_once()
    assert caught.value is private_error
    clock[0] += 4
    snapshot = diagnostics.snapshot()
    assert snapshot.worker.last_poll_age_seconds == 4
    assert snapshot.worker.last_fault is not None
    assert snapshot.worker.last_fault.category == "database_access"
    assert snapshot.worker.last_fault.boundary == "claim"
    assert snapshot.worker.last_fault.age_seconds == 4
    assert "synthetic-private-claim-error" not in json.dumps(asdict(snapshot))
