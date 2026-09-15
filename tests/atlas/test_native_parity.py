"""Run the native helper against the same fixture-only workspace acceptance cases.

Windows CI uses Windows PowerShell 5.1. ATLAS_POWERSHELL permits an explicit local
PowerShell 7 executable for additional cross-platform checks, not a 5.1 claim.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "atlas/atlas-plugin/scripts/atlas-local.ps1"
_spec = importlib.util.spec_from_file_location(
    "atlas_workspace_cases", Path(__file__).with_name("test_workspace.py")
)
assert _spec and _spec.loader
cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cases)
NATIVE = os.environ.get("ATLAS_POWERSHELL") or (
    shutil.which("powershell.exe") if os.name == "nt" else None
)
pytestmark = pytest.mark.skipif(not NATIVE, reason="Native PowerShell runtime unavailable")


def native_run(*args: str, success: bool = True) -> dict[str, Any]:
    result = subprocess.run(
        [
            str(NATIVE),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HELPER),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if success:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    assert result.returncode != 0
    return {"error": result.stderr}


@pytest.mark.parametrize("case", [name for name in vars(cases) if name.startswith("test_")])
def test_native_workspace_parity(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cases, "run", native_run)
    getattr(cases, case)(tmp_path)


def test_native_selection_preserves_draft_and_attaches_model(tmp_path: Path) -> None:
    root = tmp_path / "work"
    native_run("session-init", "--root", str(root), "--tenant", "TENANT_A", "--tenant-id", "1")
    native_run(
        "model-select",
        "--session",
        str(root),
        "--model-id",
        "41",
        "--model-name",
        "Customer Model",
    )
    native_run(
        "model-select",
        "--session",
        str(root),
        "--model-id",
        "42",
        "--model-name",
        "Other",
        success=False,
    )
    first = native_run("task-add", "--session", str(root), "--outcome", "Author")
    second = native_run("task-add", "--session", str(root), "--outcome", "Review")
    native_run("task-select", "--session", str(root), "--task", first["task"])
    assert native_run("status", "--session", str(root))["session"]["active_task"] == first["task"]
    assert first["task"] != second["task"]
    cases.fixtures.write_metadata_snapshot(root)
    copied = native_run(
        "copy",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"CRM"}',
        "--expected-digest",
        "empty",
    )
    draft_path = root / "metadata-change-set/source_object.json"
    draft = json.loads(draft_path.read_text())
    draft[0]["object_description"] = "Local description remains after another copy."
    draft_path.write_text(json.dumps(draft))
    digest = native_run("review", "--session", str(root), "--area", "metadata")["digest"]
    assert digest != copied["digest"]
    native_run(
        "copy",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"CRM"}',
        "--expected-digest",
        digest,
    )
    selected = native_run(
        "select",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--view",
        "effective",
    )
    assert selected["records"][0]["object_description"] == draft[0]["object_description"]


def test_native_new_model_policy_rejects_unsupported_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cases, "run", native_run)
    root = cases.workspace(tmp_path)
    pending = root / "model-change-set"
    pending.mkdir()
    (pending / "logical_entity.json").write_text(
        json.dumps(
            [
                {
                    "logical_entity_name": "bad_name",
                    "logical_entity_status": "active",
                    "logical_entity_type": "master",
                    "logical_entity_dependency_order": 1,
                    "submodels": [],
                    "sources": [],
                }
            ]
        )
    )
    result = native_run("validate", "--session", str(root), "--area", "model")
    assert not result["valid"]
    codes = {item["code"] for item in result["issues"]}
    assert {"model.naming-policy", "model.own-surrogate", "model.audit-order"} <= codes


def test_native_profile_import_complete_and_rejects_raw_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.atlas import test_profiling_runtime as profile
    from tests.atlas import test_workspace as shared

    monkeypatch.setattr(shared, "run", native_run)
    monkeypatch.setattr(profile, "run", native_run)
    profile.test_profile_runtime_groups_sql_and_imports_exact_record_contract(tmp_path / "complete")
    profile.test_profile_runtime_rejects_incomplete_or_unbound_results_before_writing(
        tmp_path / "reject", "unknown_column"
    )


def test_native_apply_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.atlas import test_lifecycle as lifecycle
    from tests.atlas import test_workspace as shared

    monkeypatch.setattr(shared, "run", native_run)
    monkeypatch.setattr(lifecycle, "run", native_run)
    lifecycle.test_apply_needs_stage_server_review_and_separate_approval(tmp_path)


def test_native_profile_rejects_unbound_plan_before_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.atlas import test_profiling_runtime as profile
    from tests.atlas import test_workspace as shared

    monkeypatch.setattr(shared, "run", native_run)
    monkeypatch.setattr(profile, "run", native_run)
    root, plan_path, plan, results = profile.planned_workspace(tmp_path)
    for corruption in ("missing_inputs", "wrong_object", "duplicate_index"):
        changed = json.loads(json.dumps(plan))
        if corruption == "missing_inputs":
            changed["inputs"] = []
        elif corruption == "wrong_object":
            changed["queries"][0]["attributes"][0]["object_name"] = "WrongObject"
        else:
            changed["queries"][1]["attributes"][0]["attribute_index"] = changed["queries"][0][
                "attributes"
            ][0]["attribute_index"]
        plan_path.write_text(json.dumps(changed))
        profile.import_results(root, plan_path, results, success=False)
        assert not (root / "model-change-set/profiling_profile.json").exists()
    plan_path.write_text(json.dumps(plan))
    for field, index, value in [
        ("percent_distinct", 1, "49"),
        ("min_data_length", 0, 3),
    ]:
        changed_results = json.loads(json.dumps(results))
        changed_results[0]["rows"][index][field] = value
        profile.import_results(root, plan_path, changed_results, success=False)
        assert not (root / "model-change-set/profiling_profile.json").exists()


def test_native_refresh_fences_applied_revision_without_pending_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    from uuid import uuid4

    monkeypatch.setattr(cases, "run", native_run)
    root = cases.workspace(tmp_path)
    state_path = root / ".atlas/session.json"
    state = json.loads(state_path.read_text())
    operation_id = str(uuid4())
    relative = f".atlas/tasks/{state['active_task']}.evidence/{operation_id}.json"
    (root / relative).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "id": operation_id,
                "task_id": state["active_task"],
                "area": "model",
                "owner": {"id": 1, "code": "TENANT_A", "root": "."},
                "local_digest": "a" * 64,
                "apply": {"applied": True, "model_revision": 9},
            }
        )
    )
    state["operations"] = {"model": relative}
    state["refresh_required"] = [{"area": "model", "owner_tenant_id": 1}]
    state_path.write_text(json.dumps(state))
    source = tmp_path / "download"
    cases.fixtures.write_model_snapshot(source)
    snapshot = source / "model/model-snapshot"
    snapshot_id = str(uuid4())
    cases.fixtures.write_snapshot_manifest(
        snapshot, kind="model", snapshot_id=snapshot_id, model_revision=8
    )
    archive = tmp_path / "model.zip"
    content = cases.fixtures.archive_snapshot(snapshot, archive)
    result = native_run(
        "snapshot-install",
        "--session",
        str(root),
        "--area",
        "model",
        "--archive",
        str(archive),
        "--snapshot-id",
        snapshot_id,
        "--size-bytes",
        str(len(content)),
        "--sha256",
        hashlib.sha256(content).hexdigest(),
        success=False,
    )
    assert "older" in result["error"]
