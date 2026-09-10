"""Applied authoring bytes reconcile with real server normalization, without losing edits."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from gds_etl_workbench.domain.modeling_records import LogicalEntityRecord, ProfilingProfileRecord

from tests.plugin_v2.test_gds_local_helper import (
    HELPER,
    archive_snapshot,
    run_helper,
    write_snapshot_manifest,
)


def prepare_refresh(
    root: Path,
    dataset: str,
    *,
    average: str | float = 1.5,
    collections: bool = False,
) -> tuple[Path, Path, dict[str, object]]:
    initialized = run_helper("session-init", "--root", str(root), "--tenant", "TENANT_A")
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    key = dict(
        tenant_code="TENANT_A",
        system_code="FIXTURE",
        connection_code="MAIN",
        object_schema="fixture",
        object_name="Sample",
    )
    if dataset == "logical_entity":
        row_type = LogicalEntityRecord
        record = dict(
            logical_entity_name="Sample",
            logical_entity_definition="Synthetic entity.",
            logical_entity_type="core",
            logical_entity_type_detail=None,
            logical_entity_grain="One sample.",
            logical_entity_dependency_order=0,
            logical_entity_confidence="high",
            logical_entity_status="active",
            logical_entity_is_locked=False,
            submodels=[],
            sources=[
                dict(
                    support_source_type="object",
                    source_object=key,
                    rationale="Synthetic source.",
                    status="active",
                    is_locked=False,
                )
            ],
        )
        canonical = ["logical_entity_name"]
        if collections:
            record["sources"][0]["source_order"] = 2
            record["sources"].append(
                {
                    "support_source_type": "object",
                    "source_object": {**key, "object_name": "Other"},
                    "source_order": 1,
                    "rationale": "Additional synthetic source.",
                    "status": "active",
                    "is_locked": False,
                }
            )
            record["submodels"] = [
                {
                    "submodel_name": name,
                    "membership_status": "active",
                    "membership_is_locked": False,
                }
                for name in ("Zeta", "Alpha")
            ]
    else:
        row_type = ProfilingProfileRecord
        record = dict(
            **key,
            attribute_name="Id",
            row_count=4,
            non_null_count=4,
            null_count=0,
            blank_count=0,
            distinct_count=4,
            min_data_length=1,
            max_data_length=2,
            avg_data_length=average,
            percent_populated=100,
            percent_duplicates=0,
            percent_null=0,
            percent_blank=0,
            percent_distinct=100,
        )
        canonical = [*key, "attribute_name"]
    normalized = json.loads(row_type.model_validate_json(json.dumps(record)).model_dump_json())
    snapshot = session / "model" / "model-snapshot"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    descriptor = dict(
        name=dataset,
        record_type=dataset,
        canonical_key=canonical,
        row_count=1,
        rows_file=f"data/{dataset}.jsonl",
        schema_file=f"schemas/{dataset}.json",
    )
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "model",
                "sections": [{"name": "fixture", "datasets": [descriptor]}],
            }
        )
    )
    (snapshot / descriptor["rows_file"]).write_text(json.dumps(normalized) + "\n")
    (snapshot / descriptor["schema_file"]).write_text(json.dumps(row_type.model_json_schema()))
    write_snapshot_manifest(snapshot, kind="model", snapshot_id="snapshot-new", model_revision=2)
    (session / "session.json").write_text(
        json.dumps(
            {
                "current": None,
                "tasks": [["01", "model", "Synthetic fixture", "applied"]],
                "stale": ["model"],
            }
        )
    )
    (session / "tasks" / "01.applied.json").write_text('["model","snapshot-old",1]')
    pending = session / "model-change-set" / f"{dataset}.json"
    pending.write_text(json.dumps([record]))
    content = pending.read_bytes()
    digest = hashlib.sha256(
        f"{pending.name}\0{len(content)}\0".encode() + content,
    ).hexdigest()
    (session / "tasks" / "01.accept.json").write_text(
        json.dumps(
            [
                digest,
                "valid",
                "snapshot-old",
                1,
            ]
        )
    )
    return session, pending, normalized


@pytest.mark.parametrize("runtime", ["javascript", "powershell"])
@pytest.mark.parametrize("dataset", ["logical_entity", "profiling_profile"])
@pytest.mark.parametrize("scenario", ["normalized", "changed", "undeclared_null", "edited_bytes"])
def test_refresh_normalizes_only_server_representations(tmp_path, runtime, dataset, scenario):
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if runtime == "powershell" and not powershell:
        pytest.skip("PowerShell is not installed")
    session, pending, normalized = prepare_refresh(tmp_path, dataset)
    original = pending.read_bytes()
    if scenario == "changed":
        if dataset == "logical_entity":
            normalized["logical_entity_definition"] = "Unaccepted edited definition."
        else:
            normalized["avg_data_length"] = "1.500001"
    elif scenario == "undeclared_null":
        normalized["undeclared"] = None
    elif scenario == "edited_bytes":
        # Even equivalent formatting changes must not weaken the accepted byte digest.
        pending.write_bytes(original + b"\n")
    snapshot = session / "model" / "model-snapshot"
    (snapshot / "data" / f"{dataset}.jsonl").write_text(json.dumps(normalized) + "\n")
    write_snapshot_manifest(snapshot, kind="model", snapshot_id="snapshot-new", model_revision=2)
    arguments = ["snapshot-refresh", "--session", str(session), "--area", "model"]
    command = (
        ["node", str(HELPER)]
        if runtime == "javascript"
        else [powershell, "-NoProfile", "-File", str(HELPER.with_suffix(".ps1"))]
    )
    result = subprocess.run([*command, *arguments], capture_output=True, text=True, timeout=30)
    state = json.loads((session / "session.json").read_text())
    if scenario == "normalized":
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["retired"] == 1
        assert not pending.exists()
        assert "stale" not in state
    else:
        assert result.returncode != 0
        assert pending.exists()
        assert state["stale"] == ["model"]
        expected = "accepted digest" if scenario == "edited_bytes" else "exact applied local record"
        assert expected in result.stderr


@pytest.mark.parametrize("runtime", ["javascript", "powershell"])
@pytest.mark.parametrize("scenario", ["reordered", "order_changed", "content_changed", "duplicate"])
def test_refresh_matches_owned_collections_without_ignoring_changes(tmp_path, runtime, scenario):
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if runtime == "powershell" and not powershell:
        pytest.skip("PowerShell is not installed")
    session, pending, normalized = prepare_refresh(tmp_path, "logical_entity", collections=True)
    normalized["sources"].reverse()
    normalized["submodels"].reverse()
    if scenario == "order_changed":
        normalized["sources"][0]["source_order"] = 3
    elif scenario == "content_changed":
        normalized["sources"][0]["rationale"] = "Different source meaning."
    elif scenario == "duplicate":
        normalized["sources"][1] = normalized["sources"][0]
    snapshot = session / "model" / "model-snapshot"
    (snapshot / "data" / "logical_entity.jsonl").write_text(json.dumps(normalized) + "\n")
    write_snapshot_manifest(snapshot, kind="model", snapshot_id="snapshot-new", model_revision=2)
    command = (
        ["node", str(HELPER)]
        if runtime == "javascript"
        else [powershell, "-NoProfile", "-File", str(HELPER.with_suffix(".ps1"))]
    )
    result = subprocess.run(
        [
            *command,
            "snapshot-refresh",
            "--session",
            str(session),
            "--area",
            "model",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (result.returncode == 0) is (scenario == "reordered"), result.stderr
    assert pending.exists() is (scenario != "reordered")


@pytest.mark.parametrize("runtime", ["javascript", "powershell"])
@pytest.mark.parametrize(
    ("local", "server", "matches"),
    [
        ("1.500000", "1.5", True),
        ("99999999999999.000001", "99999999999999.000002", False),
    ],
)
def test_refresh_compares_decimals_without_float_rounding(
    tmp_path, runtime, local, server, matches
):
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if runtime == "powershell" and not powershell:
        pytest.skip("PowerShell is not installed")
    session, pending, normalized = prepare_refresh(tmp_path, "profiling_profile", average=local)
    normalized["avg_data_length"] = server
    snapshot = session / "model" / "model-snapshot"
    (snapshot / "data" / "profiling_profile.jsonl").write_text(json.dumps(normalized) + "\n")
    write_snapshot_manifest(snapshot, kind="model", snapshot_id="snapshot-new", model_revision=2)
    command = (
        ["node", str(HELPER)]
        if runtime == "javascript"
        else [powershell, "-NoProfile", "-File", str(HELPER.with_suffix(".ps1"))]
    )
    result = subprocess.run(
        [
            *command,
            "snapshot-refresh",
            "--session",
            str(session),
            "--area",
            "model",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (result.returncode == 0) is matches, result.stderr
    assert pending.exists() is not matches


@pytest.mark.parametrize(
    "failure",
    [
        "backup_cleanup",
        "retired_cleanup",
        "state_commit",
        "pending_restore",
        "directory_locked",
    ],
)
def test_snapshot_install_failure_preserves_applied_work(tmp_path: Path, failure: str):
    session, pending, _ = prepare_refresh(tmp_path, "logical_entity")
    original = pending.read_bytes()
    snapshot = session / "model" / "model-snapshot"
    new_id = "00000000-0000-4000-8000-000000000321"
    write_snapshot_manifest(snapshot, kind="model", snapshot_id=new_id, model_revision=2)
    archive = tmp_path / "next.zip"
    content = archive_snapshot(snapshot, archive)
    write_snapshot_manifest(snapshot, kind="model", snapshot_id="snapshot-old", model_revision=1)
    fault = tmp_path / "fault.cjs"
    fault.write_text("""
const fs = require('node:fs');
const path = require('node:path');
const mode = process.env.GDS_TEST_FAILURE;
const rm = fs.rmSync, rename = fs.renameSync;
fs.rmSync = function(target, ...args) {
  if ((mode === 'backup_cleanup' && String(target).endsWith('-previous')) ||
      (mode === 'retired_cleanup' && path.basename(String(target)).startsWith('.model-retired-'))) {
    throw Object.assign(new Error('Synthetic locked backup'), {code:'EBUSY'});
  }
  return rm.call(this, target, ...args);
};
fs.renameSync = function(source, target, ...args) {
  if ((mode === 'directory_locked' && String(target).endsWith('-previous')) ||
      (['state_commit', 'pending_restore'].includes(mode) &&
       path.basename(String(target)) === 'session.json' &&
       !JSON.parse(fs.readFileSync(source, 'utf8')).stale) ||
      (mode === 'pending_restore' && path.basename(String(source)) === 'records')) {
    throw Object.assign(new Error('Synthetic locked directory'), {code:'EBUSY'});
  }
  return rename.call(this, source, target, ...args);
};
""")
    # Environment carries only a synthetic injection selector, never a connection value.
    result = subprocess.run(
        [
            "node",
            "--require",
            str(fault),
            str(HELPER),
            "snapshot-install",
            "--session",
            str(session),
            "--area",
            "model",
            "--archive",
            str(archive),
            "--snapshot-id",
            new_id,
            "--size-bytes",
            str(len(content)),
            "--sha256",
            hashlib.sha256(content).hexdigest(),
        ],
        env={**os.environ, "GDS_TEST_FAILURE": failure},
        capture_output=True,
        text=True,
        timeout=30,
    )
    state = json.loads((session / "session.json").read_text())
    manifest = json.loads((snapshot / "manifest.json").read_text())
    if failure in {"backup_cleanup", "retired_cleanup"}:
        assert result.returncode == 0, result.stderr
        assert manifest["snapshot_id"] == new_id
        assert "stale" not in state
        assert not pending.exists()
        assert json.loads(result.stdout)["cleanup_pending"]
    else:
        assert result.returncode != 0
        assert manifest["snapshot_id"] == "snapshot-old"
        if failure == "pending_restore":
            saved = list(session.glob(".model-retired-*/records/logical_entity.json"))
            assert len(saved) == 1 and saved[0].read_bytes() == original
            assert "local records are preserved" in result.stderr
        else:
            assert pending.read_bytes() == original
        assert state["stale"] == ["model"]
        if failure == "directory_locked":
            assert "Close Workbench" in result.stderr
            assert "retry" in result.stderr
