from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from tests.atlas.test_workspace import run, workspace


def prepare(root: Path) -> tuple[Path, dict[str, Any]]:
    copied = run(
        "copy",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        "{}",
        "--expected-digest",
        "empty",
    )
    accepted = run(
        "accept",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--digest",
        copied["digest"],
        "--backend-profile",
        "local",
        "--endpoint-sha256",
        "a" * 64,
    )
    run(
        "draft-cache",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--id",
        str(uuid4()),
        "--revision",
        "0",
        "--status",
        "active",
    )
    run("prepare-stage-request", "--session", str(root), "--area", "metadata")
    path = root / accepted["path"]
    operation = json.loads(path.read_text())
    return path, operation


def staged_fixture(path: Path, operation: dict[str, Any]) -> None:
    # Simulate the extension's separately tested verified receipt; no server writes.
    operation["stage_attempt"] = {"status": "verified"}
    operation["stage"] = {
        "fingerprintVerified": True,
        "acceptedDigest": operation["local_digest"],
        "status": "staged",
        "changeSetId": operation["draft"]["id"],
        "resultingRevision": 1,
        "stageFingerprint": "c" * 64,
    }
    operation["draft"]["revision"] = 1
    path.write_text(json.dumps(operation))


def test_apply_needs_stage_server_review_and_separate_approval(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    path, operation = prepare(root)
    response: dict[str, Any] = {
        "schema_version": "1.0",
        "metadata_change_set_id": operation["draft"]["id"],
        "tenant_id": 1,
        "draft_revision": 0,
        "valid": True,
        "status": "validated",
        "candidate_digest": "b" * 64,
        "error_count": 0,
        "action_review": {"actions": []},
    }
    result = tmp_path / "result.json"
    result.write_text(json.dumps(response))
    args = ["--session", str(root), "--area", "metadata", "--file", str(result)]
    assert (
        "Stage"
        in run("operation-record", *args, "--checkpoint", "validation", success=False)["error"]
    )
    staged_fixture(path, operation)
    response["draft_revision"] = 1
    result.write_text(json.dumps(response))
    run("operation-record", *args, "--checkpoint", "validation")
    validated = json.loads(path.read_text())
    review_digest = validated["server_validation"]["sha256"]
    response.update(applied=True, status="applied", action_count=1)
    result.write_text(json.dumps(response))
    run("operation-record", *args, "--checkpoint", "apply", success=False)
    response.update(status="validated")
    result.write_text(json.dumps(response))
    run(
        "operation-record",
        *args,
        "--checkpoint",
        "apply-approval",
        "--review-digest",
        review_digest,
    )
    response.update(status="applied")
    result.write_text(json.dumps(response))
    assert run("operation-record", *args, "--checkpoint", "apply")["refresh_required"]
    state = run("status", "--session", str(root))["session"]
    assert state["refresh_required"][0]["owner_tenant_id"] == 1
    run("review", "--session", str(root), "--area", "metadata", success=False)


def test_changed_files_and_unknown_stage_block_approval(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    path, operation = prepare(root)
    staged_fixture(path, operation)
    response: dict[str, Any] = {
        "metadata_change_set_id": operation["draft"]["id"],
        "tenant_id": 1,
        "draft_revision": 1,
        "valid": True,
        "status": "validated",
        "candidate_digest": "b" * 64,
        "action_review": {},
    }
    result = tmp_path / "result.json"
    result.write_text(json.dumps(response))
    args = ["--session", str(root), "--area", "metadata", "--file", str(result)]
    run("operation-record", *args, "--checkpoint", "validation")
    digest = json.loads(path.read_text())["server_validation"]["sha256"]
    pending = root / "metadata-change-set/source_object.json"
    pending.write_bytes(pending.read_bytes() + b" ")
    assert (
        "changed"
        in run(
            "operation-record",
            *args,
            "--checkpoint",
            "apply-approval",
            "--review-digest",
            digest,
            success=False,
        )["error"]
    )
    operation = json.loads(path.read_text())
    operation["stage_attempt"]["status"] = "unknown"
    path.write_text(json.dumps(operation))
    run("task-add", "--session", str(root), "--outcome", "Independent next work")
    assert (
        "Stage"
        in run(
            "accept",
            "--session",
            str(root),
            "--area",
            "metadata",
            "--digest",
            run("review", "--session", str(root), "--area", "metadata")["digest"],
            "--backend-profile",
            "local",
            "--endpoint-sha256",
            "a" * 64,
            success=False,
        )["error"]
    )


def test_effective_reads_and_copy_preserve_proposals(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    args = ["--session", str(root), "--area", "metadata", "--dataset", "source_object"]
    baseline = run("select", *args, "--where", "{}")["records"][0]
    record = {**baseline, "is_active": False}
    result = run("upsert", *args, "--record", json.dumps(record), "--expected-digest", "empty")
    run("copy", *args, "--where", "{}", "--expected-digest", result["digest"])
    assert (
        run("select", *args, "--where", "{}", "--view", "effective")["records"][0]["is_active"]
        == record["is_active"]
    )
    assert run("select", *args, "--where", "{}")["records"][0] == baseline


def test_metadata_first_can_attach_model_and_resume_task(tmp_path: Path) -> None:
    root = tmp_path / "work"
    run("session-init", "--root", str(root), "--tenant", "DEMO", "--tenant-id", "1")
    first = run("task-add", "--session", str(root), "--outcome", "Initial metadata")
    run("task-add", "--session", str(root), "--outcome", "Later work")
    run("task-select", "--session", str(root), "--task", first["task"])
    run(
        "model-select",
        "--session",
        str(root),
        "--model-id",
        "3",
        "--model-name",
        "Customers",
    )
    state = run("status", "--session", str(root))["session"]
    assert state["active_task"] == first["task"]
    assert state["model"]["id"] == 3
    run(
        "model-select",
        "--session",
        str(root),
        "--model-id",
        "4",
        "--model-name",
        "Orders",
        success=False,
    )
