"""Exercise the documented handoff with direct server responses, without a server."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from tests.atlas import test_native_parity as native
from tests.atlas import test_workspace as workspace_cases

Runner = Callable[..., dict[str, Any]]


@pytest.fixture(params=["node", "native"])
def runner(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Runner:
    if request.param == "native":
        if not native.NATIVE:
            pytest.skip("Native PowerShell runtime unavailable")
        monkeypatch.setattr(workspace_cases, "run", native.native_run)
    return workspace_cases.run


def draft_files(root: Path, area: str) -> tuple[Path, Path, dict[str, Any]]:
    backend = root / ".atlas/temp/backend.json"
    backend.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": "ready",
                "backend": {
                    "profile": "local",
                    "endpoint_sha256": "a" * 64,
                },
            }
        )
    )
    response: dict[str, Any] = {
        "schema_version": "1.0",
        f"{area}_change_set_id": str(uuid4()),
        "draft_revision": 1,
        "status": "active",
        "created": True,
        **({"tenant_id": 1} if area == "metadata" else {"model_id": 41}),
    }
    draft = root / ".atlas/temp/draft.json"
    draft.write_text(
        json.dumps(
            {
                "structuredContent": response,
                "content": [{"type": "text", "text": json.dumps(response, indent=2)}],
            }
        )
    )
    return backend, draft, response


def copy_input(run: Runner, root: Path, area: str) -> str:
    result = run(
        "copy",
        "--session",
        str(root),
        "--area",
        area,
        "--dataset",
        "source_object" if area == "metadata" else "model_details",
        "--where",
        "{}",
        "--expected-digest",
        "empty",
    )
    return str(result["digest"])


@pytest.mark.parametrize("area", ["metadata", "model"])
def test_direct_response_handoff_and_fileless_apply_approval(
    tmp_path: Path,
    runner: Runner,
    area: str,
) -> None:
    root = workspace_cases.workspace(tmp_path)
    digest = copy_input(runner, root, area)
    backend, draft, response = draft_files(root, area)
    output = root / ".atlas/temp/accepted.json"
    accepted = runner(
        "accept",
        "--session",
        str(root),
        "--area",
        area,
        "--digest",
        digest,
        "--backend-file",
        str(backend),
        "--draft-file",
        str(draft),
        "--prepare-stage",
        "true",
        "--output-file",
        str(output),
    )
    assert json.loads(output.read_text()) == accepted
    manifest = json.loads(Path(accepted["stage_manifest_path"]).read_text())
    assert manifest["accepted_digest"] == digest
    assert accepted["change_set_id"] == response[f"{area}_change_set_id"]
    assert accepted["operation_id"] == manifest["operation"]["id"]
    operation_file = root / accepted["path"]
    operation = json.loads(operation_file.read_text())
    # The extension's separately tested verified Stage is represented locally.
    operation["draft"]["revision"] = 2
    operation["stage"] = {
        "status": "staged",
        "fingerprint_verified": True,
        "accepted_digest": digest,
        "change_set_id": accepted["change_set_id"],
        "draft_revision": 2,
        "stage_fingerprint": "c" * 64,
    }
    operation["stage_attempt"] = {"status": "verified"}
    operation_file.write_text(json.dumps(operation))
    response.update(
        draft_revision=2,
        status="validated",
        valid=True,
        candidate_digest="b" * 64,
        error_count=0,
        action_review=[],
        unneeded_transport_field="do-not-retain",
    )
    result_file = root / ".atlas/temp/validation-response.json"
    result_file.write_text(
        json.dumps({"content": [{"type": "text", "text": json.dumps(response)}]})
    )
    args = ["--session", str(root), "--area", area]
    runner("operation-record", *args, "--checkpoint", "validation", "--file", str(result_file))
    operation = json.loads(operation_file.read_text())
    saved_path = root / operation["server_validation"]["path"]
    saved = json.loads(saved_path.read_text())
    assert saved["change_set_id"] == accepted["change_set_id"]
    assert "unneeded_transport_field" not in saved
    assert f"{area}_change_set_id" not in saved
    # Canonical local review can also be read directly; no manual renaming required.
    runner(
        "operation-record",
        *args,
        "--checkpoint",
        "apply-approval",
        "--file",
        str(saved_path),
        "--digest-from-operation",
        "true",
    )
    runner(
        "operation-record",
        *args,
        "--checkpoint",
        "apply-approval",
        "--digest-from-operation",
        "true",
    )
    response.update(status="applied", applied=True, action_count=1, model_revision=2)
    result_file.write_text(json.dumps(response))
    applied = runner("operation-record", *args, "--checkpoint", "apply", "--file", str(result_file))
    assert applied["refresh_required"]
    assert applied["operation_id"] == accepted["operation_id"]


def test_preparation_imports_draft_and_reuses_cache_without_digest_copying(
    tmp_path: Path,
    runner: Runner,
) -> None:
    root = workspace_cases.workspace(tmp_path)
    contract = runner("command-contract", "--command", "accept")
    assert "--backend-file" in contract["usage"]
    assert "--prepare-stage" in contract["usage"]
    digest = copy_input(runner, root, "metadata")
    backend, draft, response = draft_files(root, "metadata")
    args = ["--session", str(root), "--area", "metadata"]
    accepted = runner("accept", *args, "--digest", digest, "--backend-file", str(backend))
    prepared = runner("prepare-stage-request", *args, "--draft-file", str(draft))
    assert prepared == runner("prepare-stage-request", *args)
    cached = runner("draft-cache", *args, "--file", str(draft))
    assert cached["change_set_id"] == response["metadata_change_set_id"]
    assert cached["draft_revision"] == 1
    pending = root / "metadata-change-set/source_object.json"
    pending.write_bytes(pending.read_bytes() + b" ")
    operation_file = root / accepted["path"]
    before = operation_file.read_bytes()
    runner("prepare-stage-request", *args, success=False)
    assert operation_file.read_bytes() == before


def test_accept_rejects_invalid_draft_or_output_before_acknowledgement(
    tmp_path: Path,
    runner: Runner,
) -> None:
    root = workspace_cases.workspace(tmp_path)
    digest = copy_input(runner, root, "metadata")
    backend, draft, response = draft_files(root, "metadata")
    args = [
        "--session",
        str(root),
        "--area",
        "metadata",
        "--digest",
        digest,
        "--backend-file",
        str(backend),
        "--prepare-stage",
        "true",
    ]
    state_file = root / ".atlas/session.json"
    before = state_file.read_bytes()
    runner("accept", *args, success=False)
    for invalid in [
        {**response, "tenant_id": 2},
        {**response, "tenant_id": "1"},
        {**response, "schema_version": 1},
        {"structuredContent": [response]},
        {**response, "metadata_change_set_id": [response["metadata_change_set_id"]]},
        {**response, "change_set_id": str(uuid4())},
        {**response, "model_change_set_id": response["metadata_change_set_id"]},
        {**response, "status": "applied"},
        {"isError": True, "structuredContent": response},
        {"structuredContent": response, "content": [{"type": "text", "text": "{}"}]},
    ]:
        draft.write_text(json.dumps(invalid))
        runner("accept", *args, "--draft-file", str(draft), success=False)
        assert state_file.read_bytes() == before
    draft.write_text(json.dumps(response) + "\n" + json.dumps(response))
    runner("accept", *args, "--draft-file", str(draft), success=False)
    draft.write_text(json.dumps(response))
    for output in [
        state_file,
        root / ".atlas/temp/../session.json",
        root / "outside.json",
        backend,
    ]:
        runner(
            "accept", *args, "--draft-file", str(draft), "--output-file", str(output), success=False
        )
        assert state_file.read_bytes() == before


def test_reaccept_changed_unstaged_content_rebinds_draft_digest(
    tmp_path: Path,
    runner: Runner,
) -> None:
    root = workspace_cases.workspace(tmp_path)
    digest = copy_input(runner, root, "metadata")
    backend, draft, _ = draft_files(root, "metadata")
    args = [
        "--session",
        str(root),
        "--area",
        "metadata",
        "--backend-file",
        str(backend),
        "--draft-file",
        str(draft),
        "--prepare-stage",
        "true",
    ]
    initial = runner("accept", *args, "--digest", digest)
    pending = root / "metadata-change-set/source_object.json"
    pending.write_bytes(pending.read_bytes() + b" ")
    reviewed = runner("review", "--session", str(root), "--area", "metadata")
    assert reviewed["digest"] != digest
    accepted = runner("accept", *args, "--digest", reviewed["digest"])
    operation = json.loads((root / accepted["path"]).read_text())
    manifest = json.loads(Path(accepted["stage_manifest_path"]).read_text())
    assert accepted["operation_id"] != initial["operation_id"]
    assert operation["draft"]["digest"] == operation["local_digest"] == reviewed["digest"]
    assert manifest["failed_retry"] is False
    assert manifest["accepted_digest"] == reviewed["digest"]


def test_operation_digest_shortcut_preserves_review_and_stage_guards(
    tmp_path: Path,
    runner: Runner,
) -> None:
    root = workspace_cases.workspace(tmp_path)
    digest = copy_input(runner, root, "metadata")
    backend, draft, response = draft_files(root, "metadata")
    args = ["--session", str(root), "--area", "metadata"]
    accepted = runner(
        "accept",
        *args,
        "--digest",
        digest,
        "--backend-file",
        str(backend),
        "--draft-file",
        str(draft),
        "--prepare-stage",
        "true",
    )
    operation_file = root / accepted["path"]
    operation = json.loads(operation_file.read_text())
    operation["stage"] = {
        "status": "staged",
        "fingerprint_verified": True,
        "accepted_digest": digest,
        "change_set_id": response["metadata_change_set_id"],
        "draft_revision": 1,
        "stage_fingerprint": "c" * 64,
        "datasets": [{"dataset": "source_object", "recordCount": 1}],
    }
    operation_file.write_text(json.dumps(operation))
    response.update(
        status="validated", valid=True, candidate_digest="b" * 64, error_count=0, action_review=[]
    )
    validation_file = root / ".atlas/temp/validation.json"
    validation_file.write_text(json.dumps(response))
    runner("operation-record", *args, "--checkpoint", "validation", "--file", str(validation_file))
    good = operation_file.read_bytes()
    operation = json.loads(good)
    assert operation["stage"]["datasets"] == [{"dataset": "source_object", "record_count": 1}]
    approval = [
        "operation-record",
        *args,
        "--checkpoint",
        "apply-approval",
        "--digest-from-operation",
        "true",
    ]
    review_file = root / operation["server_validation"]["path"]
    review_bytes = review_file.read_bytes()
    review_file.write_bytes(review_bytes + b" ")
    runner(*approval, success=False)
    review_file.write_bytes(review_bytes)
    pending = root / "metadata-change-set/source_object.json"
    pending_bytes = pending.read_bytes()
    pending.write_bytes(pending_bytes + b" ")
    runner(*approval, success=False)
    pending.write_bytes(pending_bytes)
    operation["stage"]["acceptedDigest"] = "f" * 64
    operation_file.write_text(json.dumps(operation))
    runner(*approval, success=False)
    operation_file.write_bytes(good)
    runner(*approval, "--review-digest", "f" * 64, success=False)
    runner(*approval)


def test_optional_export_failure_preserves_successful_command(tmp_path: Path) -> None:
    root = workspace_cases.workspace(tmp_path)
    injection = tmp_path / "fail-export.cjs"
    injection.write_text(
        "require('node:fs').linkSync = () => { throw Error('fixture export failure'); };\n"
    )
    output = root / ".atlas/temp/new-task.json"
    result = subprocess.run(
        [
            "node",
            "--require",
            str(injection),
            str(workspace_cases.HELPER),
            "task-add",
            "--session",
            str(root),
            "--outcome",
            "Durable task despite export failure",
            "--output-file",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["receipt_export"]["code"] == "RECEIPT_EXPORT_FAILED"
    assert (root / f".atlas/tasks/{response['task']}.json").exists()
    assert not output.exists()
