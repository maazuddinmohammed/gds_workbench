from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "atlas/atlas-plugin/scripts/atlas-local.js"
_fixture_spec = importlib.util.spec_from_file_location(
    "gds_snapshot_fixtures", ROOT / "tests/plugin_v2/test_gds_local_helper.py"
)
assert _fixture_spec and _fixture_spec.loader
fixtures = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(fixtures)


def run(*args: str, success: bool = True) -> dict[str, Any]:
    result = subprocess.run(
        ["node", str(HELPER), *args], capture_output=True, text=True, timeout=20
    )
    if success:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    assert result.returncode != 0
    return {"error": result.stderr}


def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    run(
        "session-init",
        "--root",
        str(root),
        "--tenant",
        "TENANT_A",
        "--tenant-id",
        "1",
        "--model-id",
        "41",
        "--model-name",
        "Customer Model",
    )
    run("task-add", "--session", str(root), "--outcome", "Review customer metadata")
    fixtures.write_metadata_snapshot(root)
    fixtures.write_model_snapshot(root)
    return root


def test_initialize_reuse_flexible_task_and_owner_roots(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    state = run("status", "--session", str(root))
    task = state["tasks"][0]
    changed = run(
        "task-update",
        "--session",
        str(root),
        "--task",
        task["id"],
        "--progress",
        "Investigating; next inspect relationships.",
        "--expected-digest",
        task["digest"],
    )
    assert changed["digest"] != task["digest"]
    run(
        "task-update",
        "--session",
        str(root),
        "--task",
        task["id"],
        "--progress",
        "stale",
        "--expected-digest",
        task["digest"],
        success=False,
    )
    assert (
        run(
            "owner-add",
            "--session",
            str(root),
            "--tenant-id",
            "2",
            "--tenant",
            "TENANT_B",
        )["owner"]["root"]
        == "metadata-owners/tenant-2"
    )
    assert run("status", "--session", str(root))["session"]["tenant"]["id"] == 1
    assert not (root / "session.json").exists()
    run(
        "session-init",
        "--root",
        str(root),
        "--tenant",
        "DIFFERENT",
        "--tenant-id",
        "2",
        success=False,
    )


def test_review_accept_stage_request_uses_operation_evidence(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    copied = run(
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
    validated = run("validate", "--session", str(root), "--area", "metadata")
    assert validated["valid"]
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
    change_id = str(uuid4())
    run(
        "draft-cache",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--id",
        change_id,
        "--revision",
        "0",
        "--status",
        "active",
    )
    request = run("prepare-stage-request", "--session", str(root), "--area", "metadata")
    manifest = json.loads(Path(request["manifest"]).read_text(encoding="utf-8"))
    assert manifest["operation"]["path"] == accepted["path"]
    assert manifest["kind"] == "atlas-stage-request"
    assert manifest["owner"] == {"id": 1, "code": "TENANT_A", "root": "."}
    assert manifest["datasets"][0]["payload_file"].startswith("metadata-change-set/")
    operation = json.loads((root / accepted["path"]).read_text(encoding="utf-8"))
    assert operation["validation"]["report_path"].endswith(".validation.json")
    assert operation["stage_request"]["sha256"]
    pending = root / manifest["datasets"][0]["payload_file"]
    pending.write_bytes(pending.read_bytes() + b" ")
    run(
        "prepare-stage-request",
        "--session",
        str(root),
        "--area",
        "metadata",
        success=False,
    )


def test_owner_snapshot_mismatch_and_symlink_are_rejected(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    run("owner-add", "--session", str(root), "--tenant-id", "2", "--tenant", "TENANT_B")
    owner_root = root / "metadata-owners/tenant-2"
    fixtures.write_metadata_snapshot(owner_root)
    run(
        "inspect",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--owner",
        "2",
        success=False,
    )
    (root / ".atlas/tasks/linked.json").symlink_to(root / ".atlas/session.json")
    run("status", "--session", str(root), success=False)


def test_snapshot_install_checks_hash_and_archive_paths(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    source = tmp_path / "download"
    fixtures.write_metadata_snapshot(source)
    snapshot_id = str(uuid4())
    snapshot = source / "metadata/metadata-snapshot"
    fixtures.write_snapshot_manifest(snapshot, kind="metadata", snapshot_id=snapshot_id)
    archive = tmp_path / "snapshot.zip"
    content = fixtures.archive_snapshot(snapshot, archive)
    import hashlib

    result = run(
        "snapshot-install",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--archive",
        str(archive),
        "--snapshot-id",
        snapshot_id,
        "--size-bytes",
        str(len(content)),
        "--sha256",
        hashlib.sha256(content).hexdigest(),
    )
    assert result["snapshot_id"] == snapshot_id
    assert run("inspect", "--session", str(root), "--area", "metadata")["id"] == snapshot_id


def test_dbml_cli_validates_effective_graph_and_preserves_previous_export_on_failure(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    snapshot = root / "model/model-snapshot"
    entity: dict[str, Any] = {
        "logical_entity_name": "Customer",
        "logical_entity_status": "active",
        "logical_entity_type": "master",
        "logical_entity_dependency_order": 1,
        "submodels": [],
        "sources": [],
    }
    attribute: dict[str, Any] = {
        "logical_entity_name": "Customer",
        "logical_attribute_name": "CustomerID",
        "logical_attribute_status": "active",
        "logical_attribute_data_type": "BIGINT",
        "logical_attribute_ordinal_position": 1,
        "logical_attribute_is_nullable": False,
        "logical_attribute_is_primary_key": True,
        "logical_attribute_is_natural_key": False,
        "logical_attribute_is_surrogate_key": True,
        "logical_attribute_is_audit_column": False,
        "sources": [],
    }
    (snapshot / "data/logical_entity.jsonl").write_text(json.dumps(entity) + "\n")
    (snapshot / "data/logical_attribute.jsonl").write_text(json.dumps(attribute) + "\n")
    fixtures.write_snapshot_manifest(
        snapshot, kind="model", snapshot_id="model-snapshot-01", model_revision=8
    )
    pending = root / "model-change-set"
    pending.mkdir()
    new_attribute = {
        **attribute,
        "logical_attribute_name": "CustomerName",
        "logical_attribute_data_type": "STRING",
        "logical_attribute_ordinal_position": 2,
        "logical_attribute_is_primary_key": False,
        "logical_attribute_is_surrogate_key": False,
    }
    (pending / "logical_attribute.json").write_text(json.dumps([new_attribute]))
    result = run("generate-dbml", "--session", str(root), "--area", "model")
    exported = root / "model-dbml/logical_complete.dbml"
    before = exported.read_text()
    assert "CustomerID" in before and "CustomerName" in before
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["draft_digest"] == result["draft_digest"]
    assert {item["area"] for item in manifest["inputs"]} == {"model", "metadata"}
    (pending / "logical_attribute.json").write_text(json.dumps([new_attribute, new_attribute]))
    run("generate-dbml", "--session", str(root), "--area", "model", success=False)
    assert exported.read_text() == before


def test_cli_validation_report_matches_workbench_owner_and_evidence_contract(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    result = run("validate", "--session", str(root), "--area", "model")
    assert result["run_by"] == "agent"
    assert result["owner_tenant_id"] == 1
    assert result["checks"]
    assert all(
        {"manifest_path", "manifest_sha256", "owner_tenant_id"} <= item.keys()
        for item in result["inputs"]
    )
    assert result["report"].startswith(".atlas/tasks/")
    assert result["report"].endswith("/model-1-validation.json")


def test_missing_metadata_owner_blocks_model_edits_but_not_independent_metadata(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    run("owner-add", "--session", str(root), "--tenant-id", "2", "--tenant", "TENANT_B")
    context_only = run("validate", "--session", str(root), "--area", "model")
    assert context_only["valid"]
    missing = [i for i in context_only["issues"] if i["code"] == "metadata_owner_snapshot_missing"]
    assert len(missing) == 1 and missing[0]["severity"] == "warning"
    pending = root / "model-change-set"
    pending.mkdir(exist_ok=True)
    (pending / "logical_entity.json").write_text(
        json.dumps([{"logical_entity_name": "Customer", "logical_entity_status": "inactive"}])
    )
    result = run("validate", "--session", str(root), "--area", "model")
    assert not result["valid"]
    assert any(
        i["code"] == "metadata_owner_snapshot_missing" and i["severity"] == "error"
        for i in result["issues"]
    )
    run(
        "accept",
        "--session",
        str(root),
        "--area",
        "model",
        "--digest",
        result["digest"],
        "--backend-profile",
        "local",
        "--endpoint-sha256",
        "a" * 64,
        success=False,
    )
    assert run("validate", "--session", str(root), "--area", "metadata")["valid"]


def test_metadata_task_binds_its_model_snapshot_before_validation_and_acceptance(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
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
    inputs = run("validate", "--session", str(root), "--area", "model")["inputs"]
    binding = next(item for item in inputs if item["area"] == "model")
    task_id = json.loads((root / ".atlas/session.json").read_text())["active_task"]
    task_path = root / f".atlas/tasks/{task_id}.json"
    task = json.loads(task_path.read_text())
    task["inputs"] = {"snapshots": [binding]}
    task_path.write_text(json.dumps(task))
    result = run("validate", "--session", str(root), "--area", "metadata")
    assert binding in result["inputs"]
    arguments = (
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
    accepted = run(*arguments)
    operation = root / accepted["path"]
    before = operation.read_bytes()
    assert binding in json.loads(before)["inputs"]
    for field, value in (("manifest_sha256", "0" * 64), ("owner_tenant_id", 2)):
        task["inputs"]["snapshots"] = [{**binding, field: value}]
        task_path.write_text(json.dumps(task))
        run("validate", "--session", str(root), "--area", "metadata", success=False)
        run(*arguments, success=False)
        assert operation.read_bytes() == before


def test_model_metadata_merge_requires_matching_owner_key_contracts(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    run("owner-add", "--session", str(root), "--tenant-id", "2", "--tenant", "TENANT_B")
    owner = root / "metadata-owners/tenant-2"
    fixtures.write_metadata_snapshot(owner)
    snapshot = owner / "metadata/metadata-snapshot"
    fixtures.write_snapshot_manifest(
        snapshot, kind="metadata", snapshot_id=str(uuid4()), tenant_code="TENANT_B"
    )
    assert run("validate", "--session", str(root), "--area", "model")["valid"]
    catalog_path = snapshot / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    attributes = next(
        dataset
        for section in catalog["sections"]
        for dataset in section["datasets"]
        if dataset["name"] == "source_attribute"
    )
    attributes["canonical_key"].reverse()
    catalog_path.write_text(json.dumps(catalog))
    fixtures.write_snapshot_manifest(
        snapshot, kind="metadata", snapshot_id=str(uuid4()), tenant_code="TENANT_B"
    )
    result = run("validate", "--session", str(root), "--area", "model", success=False)
    assert "key contracts" in result["error"]


def test_generated_sql_policy_runs_before_local_acceptance(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    snapshot = root / "model/model-snapshot"
    catalog_path = snapshot / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    dataset = {
        "name": "generated_code",
        "canonical_key": ["generated_code_name"],
        "row_count": 0,
        "rows_file": "data/generated_code.jsonl",
        "schema_file": "schemas/generated_code.json",
    }
    catalog["sections"][0]["datasets"].append(dataset)
    catalog_path.write_text(json.dumps(catalog))
    (snapshot / str(dataset["rows_file"])).write_text("")
    (snapshot / str(dataset["schema_file"])).write_text(
        json.dumps(
            {
                "type": "object",
                "x-gds-change-set-eligible": True,
                "required": ["generated_code_name", "artifact_type", "generated_code_content"],
            }
        )
    )
    fixtures.write_snapshot_manifest(
        snapshot, kind="model", snapshot_id=str(uuid4()), model_revision=8
    )
    pending = root / "model-change-set"
    pending.mkdir()
    for sql, rule in (
        ("SELECT * FROM bronze.Customer", "code.projection"),
        ("DELETE FROM silver.Customer", "code.statements"),
    ):
        (pending / "generated_code.json").write_text(
            json.dumps(
                [
                    {
                        "generated_code_name": "Customer",
                        "artifact_type": "sql_file",
                        "generated_code_status": "active",
                        "generated_code_content": sql,
                    }
                ]
            )
        )
        result = run("validate", "--session", str(root), "--area", "model")
        assert not result["valid"]
        assert any(issue["code"] == rule for issue in result["issues"])
        run(
            "accept",
            "--session",
            str(root),
            "--area",
            "model",
            "--digest",
            result["digest"],
            "--backend-profile",
            "local",
            "--endpoint-sha256",
            "a" * 64,
            success=False,
        )
