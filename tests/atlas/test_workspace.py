from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from gds_etl_workbench.domain.modeling_records import AnalysisResultRecord
from gds_etl_workbench.domain.snapshots.project import (
    DATASETS_BY_NAME,
    build_project_dataset_schema,
)

from tests.atlas import snapshot_fixtures as fixtures

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "atlas/atlas-plugin/scripts/atlas-local.js"


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
        "--project-id",
        "41",
        "--project-name",
        "Customer Project",
    )
    run("task-add", "--session", str(root), "--outcome", "Review customer metadata")
    fixtures.write_metadata_snapshot(root)
    fixtures.write_project_snapshot(root)
    return root


def test_selection_pages_cover_large_inventory_and_keep_canonical_keys(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    snapshot = root / "metadata/metadata-snapshot"
    rows_path = snapshot / "data/source_object.jsonl"
    original = [json.loads(line) for line in rows_path.read_text().splitlines()]
    records = [dict(original[0], object_name=f"Customer{index:03d}") for index in range(405)]
    records.insert(205, original[1])  # Filtering must count matches, not source lines.
    rows_path.write_text("\n".join(json.dumps(record) for record in records) + "\n\n")
    catalog = json.loads((snapshot / "catalog.json").read_text())
    dataset = catalog["sections"][0]["datasets"][0]
    dataset["row_count"] = len(records)
    (snapshot / "catalog.json").write_text(json.dumps(catalog))
    fixtures.write_snapshot_manifest(snapshot, kind="metadata", snapshot_id=str(uuid4()))
    before = rows_path.read_bytes()

    for view in ("snapshot", "effective"):
        args = (
            "select",
            "--session",
            str(root),
            "--area",
            "metadata",
            "--dataset",
            "source_object",
            "--where",
            '{"system_code":"crm"}',
            "--limit",
            "200",
            "--view",
            view,
            "--fields",
            '["is_active"]',
        )
        cursor = None
        names: list[str] = []
        pages: list[int] = []
        while True:
            page = run(*args, *(("--cursor", cursor) if cursor else ()))
            pages.append(page["count"])
            for record in page["records"]:
                assert set(record) == set(dataset["canonical_key"]) | {"is_active"}
                names.append(record["object_name"])
            cursor = page["next_cursor"]
            assert page["truncated"] == (cursor is not None)
            if cursor is None:
                break
        assert pages == [200, 200, 5]
        assert names == [f"Customer{index:03d}" for index in range(405)]
    assert rows_path.read_bytes() == before


def test_selection_cursor_rejects_changed_query_draft_and_baseline(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    args = (
        "select",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
    )
    page = run(*args, "--view", "effective", "--limit", "1")
    cursor = page["next_cursor"]
    for changes in (
        ("--view", "snapshot", "--limit", "1"),
        ("--view", "effective", "--limit", "2"),
        ("--view", "effective", "--limit", "1", "--where", '{"system_code":"CRM"}'),
        ("--view", "effective", "--limit", "1", "--fields", '["is_active"]'),
    ):
        result = run(*args, *changes, "--cursor", cursor, success=False)
        assert "Selection changed" in result["error"]

    draft = root / "metadata-change-set/source_object.json"
    draft.parent.mkdir(exist_ok=True)
    changed = dict(page["records"][0], is_active=False)
    draft.write_text(json.dumps([changed]))
    saved = draft.read_bytes()
    result = run(*args, "--view", "effective", "--limit", "1", "--cursor", cursor, success=False)
    assert "Selection changed" in result["error"]
    fresh = run(*args, "--view", "effective", "--limit", "1")
    assert fresh["records"][0]["is_active"] is False
    assert fresh["selection_digest"] != page["selection_digest"]

    baseline = run(*args, "--limit", "1")
    fixtures.write_snapshot_manifest(
        root / "metadata/metadata-snapshot", kind="metadata", snapshot_id=str(uuid4())
    )
    result = run(*args, "--limit", "1", "--cursor", baseline["next_cursor"], success=False)
    assert "Selection changed" in result["error"]
    assert draft.read_bytes() == saved


def test_logical_projection_excludes_independent_conceptual_records(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    snapshot = root / "project/project-snapshot"
    catalog = json.loads((snapshot / "catalog.json").read_text())
    dataset = {
        "name": "conceptual_object",
        "row_count": 1,
        "canonical_key": ["conceptual_object_name"],
        "rows_file": "data/conceptual_object.jsonl",
        "schema_file": "schemas/conceptual_object.schema.json",
    }
    catalog["sections"].append({"name": "conceptual", "datasets": [dataset]})
    (snapshot / "catalog.json").write_text(json.dumps(catalog))
    concept = {"conceptual_object_name": "IndependentBusinessConcept"}
    (snapshot / "data/conceptual_object.jsonl").write_text(json.dumps(concept) + "\n")
    (snapshot / "schemas/conceptual_object.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"conceptual_object_name": {"type": "string"}},
                "required": ["conceptual_object_name"],
                "x-gds-change-set-eligible": True,
            }
        )
    )
    logical = {
        "logical_entity_schema_name": "silver",
        "logical_entity_name": "Customer",
    }
    (snapshot / "data/logical_entity.jsonl").write_text(json.dumps(logical) + "\n")
    fixtures.write_snapshot_manifest(
        snapshot, kind="project", snapshot_id=str(uuid4()), project_revision=8
    )
    draft = root / "project-change-set"
    draft.mkdir(exist_ok=True)
    (draft / "conceptual_object.json").write_text(
        json.dumps([{**concept, "conceptual_object_definition": "Separate Conceptual edit"}])
    )
    args = (
        "select",
        "--session",
        str(root),
        "--area",
        "project",
        "--view",
        "effective",
    )
    assert "--dataset is required" in run(*args, success=False)["error"]
    selected = run(*args, "--dataset", "logical_entity", "--fields", '["logical_entity_name"]')
    assert selected["records"] == [logical]
    assert selected["next_cursor"] is None


def test_invalid_projection_and_cursor_do_not_change_workspace(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    before = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    args = (
        "select",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
    )
    for fields in ('["made_up"]', "[]", "{}", "[true]", "null", "not json"):
        run(*args, "--fields", fields, success=False)
    for cursor in (
        "invalid",
        "v1." + "a" * 64 + ".-1",
        "v1." + "a" * 64 + ".9007199254740992",
    ):
        run(*args, "--cursor", cursor, success=False)
    run(*args, "--limit", "1.5", success=False)
    after = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    assert after == before


def test_projection_rejects_a_record_without_complete_identity(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    snapshot = root / "metadata/metadata-snapshot"
    rows = snapshot / "data/source_object.jsonl"
    records = [json.loads(line) for line in rows.read_text().splitlines()]
    del records[0]["object_schema"]
    rows.write_text("".join(json.dumps(record) + "\n" for record in records))
    fixtures.write_snapshot_manifest(snapshot, kind="metadata", snapshot_id=str(uuid4()))
    result = run(
        "select",
        "--session",
        str(root),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--fields",
        '["is_active"]',
        success=False,
    )
    assert "canonical key" in result["error"]


def test_status_is_compact_and_history_is_explicitly_paged(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    first = run("status", "--session", str(root))["tasks"][0]
    ids = {first["id"]}
    for index in range(3):
        added = run("task-add", "--session", str(root), "--outcome", f"Synthetic task {index}")
        ids.add(added["task"])
    active = run("status", "--session", str(root))
    assert active["task_count"] == 4
    assert len(active["tasks"]) == 1
    task = active["tasks"][0]
    run(
        "task-update",
        "--session",
        str(root),
        "--task",
        task["id"],
        "--progress",
        "x" * 3000,
        "--expected-digest",
        task["digest"],
    )
    compact = run("status", "--session", str(root))["tasks"][0]
    assert len(compact["progress"]) == 2000 and compact["text_truncated"]
    full = run("status", "--session", str(root), "--task", task["id"], "--detail", "full")
    assert len(full["tasks"][0]["progress"]) == 3000
    session_before = (root / ".atlas/session.json").read_bytes()
    selected = run("status", "--session", str(root), "--task", first["id"], "--detail", "full")
    assert selected["tasks"][0]["id"] == first["id"]
    assert (root / ".atlas/session.json").read_bytes() == session_before

    args = ("status", "--session", str(root), "--history", "true", "--limit", "2")
    page = run(*args)
    second = run(*args, "--cursor", page["next_cursor"])
    assert {item["id"] for item in page["tasks"] + second["tasks"]} == ids
    assert second["next_cursor"] is None
    run(
        "task-add",
        "--session",
        str(root),
        "--outcome",
        "New task invalidates traversal",
    )
    assert (
        "Selection changed" in run(*args, "--cursor", page["next_cursor"], success=False)["error"]
    )
    run(*args, "--task", first["id"], success=False)


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


def test_subagent_policy_is_saved_and_survives_task_switch_and_resume(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    session_file = root / ".atlas/session.json"
    original = session_file.read_bytes()
    initial = run("status", "--session", str(root))["session"]
    assert "subagent_policy" not in initial
    assert session_file.read_bytes() == original
    run("sql-policy", "--session", str(root), "--policy", "never")
    policy = {"mode": "custom", "model": "Provider/Model-A:1"}
    receipt = root / ".atlas/temp/policy.json"
    result = run(
        "subagent-policy",
        "--session",
        str(root),
        "--mode",
        "custom",
        "--model",
        policy["model"],
        "--output-file",
        str(receipt),
    )
    assert result["subagent_policy"] == policy
    assert json.loads(receipt.read_text())["subagent_policy"] == policy
    run("task-add", "--session", str(root), "--outcome", "Another task")
    run("task-select", "--session", str(root), "--task", initial["active_task"])
    resumed = run("session-init", "--root", str(root), "--tenant", "TENANT_A", "--tenant-id", "1")[
        "session"
    ]
    assert resumed["subagent_policy"] == policy
    assert resumed["active_task"] == initial["active_task"]
    assert resumed["project"] == initial["project"]
    assert resumed["sql"] == {"policy": "never"}
    for mode in ("auto", "current"):
        run("subagent-policy", "--session", str(root), "--mode", mode)
        saved = run("status", "--session", str(root))["session"]
        assert saved["subagent_policy"] == {"mode": mode}
        assert saved["project"] == initial["project"]


def test_invalid_subagent_policy_command_preserves_saved_choice(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    run("subagent-policy", "--session", str(root), "--mode", "current")
    session_file = root / ".atlas/session.json"
    before = session_file.read_bytes()
    invalid_arguments = [
        (),
        ("--mode", "other"),
        ("--mode", "Current"),
        ("--mode", "custom"),
        ("--mode", "auto", "--model", "Model-A"),
        ("--mode", "current", "--model-id", "Model-A"),
        *(
            ("--mode", "custom", "--model", model)
            for model in (
                "",
                " ",
                " Model-A",
                "Model-A ",
                "Model\nA",
                "\ufeffModel-A",
                "A" * 201,
            )
        ),
    ]
    for arguments in invalid_arguments:
        run("subagent-policy", "--session", str(root), *arguments, success=False)
        assert session_file.read_bytes() == before


def test_invalid_saved_subagent_policy_is_rejected_without_rewriting(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    session_file = root / ".atlas/session.json"
    initial = json.loads(session_file.read_text())
    policies: tuple[object, ...] = (
        None,
        [],
        "auto",
        {},
        {"mode": "other"},
        {"mode": "current", "model": None},
        {"mode": "custom"},
        {"mode": "custom", "model": ["A", "B"]},
        {"mode": "custom", "model": "A\nB"},
        {"mode": "auto", "fallback": "current"},
    )
    for policy in policies:
        session_file.write_text(json.dumps({**initial, "subagent_policy": policy}))
        before = session_file.read_bytes()
        run("status", "--session", str(root), success=False)
        assert session_file.read_bytes() == before


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


def test_agent_runtime_does_not_expose_or_read_user_dbml(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    export = root / "project-dbml"
    export.mkdir()
    # User-owned exports are opaque to the agent runtime, including their manifest.
    manifest = export / "manifest.json"
    diagram = export / "logical_complete.dbml"
    manifest.write_text("User-owned export; deliberately not JSON.")
    diagram.write_text("Table Customer { CustomerID bigint }")
    before = {path.name: path.read_bytes() for path in export.iterdir()}

    assert "generate-dbml" not in run("command-contract")["commands"]
    run("command-contract", "--command", "generate-dbml", success=False)
    run("generate-dbml", "--session", str(root), "--area", "project", success=False)
    run("status", "--session", str(root))
    run("inspect", "--session", str(root), "--area", "project")
    assert {path.name: path.read_bytes() for path in export.iterdir()} == before


def test_cli_validation_report_matches_workbench_owner_and_evidence_contract(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    result = run("validate", "--session", str(root), "--area", "project")
    assert result["run_by"] == "agent"
    assert result["owner_tenant_id"] == 1
    assert result["checks"]
    assert all(
        {"manifest_path", "manifest_sha256", "owner_tenant_id"} <= item.keys()
        for item in result["inputs"]
    )
    assert result["report"].startswith(".atlas/tasks/")
    assert result["report"].endswith("/project-1-validation.json")


def test_missing_metadata_owner_blocks_project_edits_but_not_independent_metadata(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    run("owner-add", "--session", str(root), "--tenant-id", "2", "--tenant", "TENANT_B")
    context_only = run("validate", "--session", str(root), "--area", "project")
    assert context_only["valid"]
    missing = [i for i in context_only["issues"] if i["code"] == "metadata_owner_snapshot_missing"]
    assert len(missing) == 1 and missing[0]["severity"] == "warning"
    pending = root / "project-change-set"
    pending.mkdir(exist_ok=True)
    (pending / "logical_entity.json").write_text(
        json.dumps(
            [
                {
                    "logical_entity_schema_name": "silver",
                    "logical_entity_name": "Customer",
                    "logical_entity_status": "inactive",
                }
            ]
        )
    )
    result = run("validate", "--session", str(root), "--area", "project")
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
        "project",
        "--digest",
        result["digest"],
        "--backend-profile",
        "local",
        "--endpoint-sha256",
        "a" * 64,
        success=False,
    )
    assert run("validate", "--session", str(root), "--area", "metadata")["valid"]


def test_metadata_task_binds_its_project_snapshot_before_validation_and_acceptance(
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
    inputs = run("validate", "--session", str(root), "--area", "project")["inputs"]
    binding = next(item for item in inputs if item["area"] == "project")
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


def test_project_metadata_merge_requires_matching_owner_key_contracts(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    run("owner-add", "--session", str(root), "--tenant-id", "2", "--tenant", "TENANT_B")
    owner = root / "metadata-owners/tenant-2"
    fixtures.write_metadata_snapshot(owner)
    snapshot = owner / "metadata/metadata-snapshot"
    fixtures.write_snapshot_manifest(
        snapshot, kind="metadata", snapshot_id=str(uuid4()), tenant_code="TENANT_B"
    )
    assert run("validate", "--session", str(root), "--area", "project")["valid"]
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
    result = run("validate", "--session", str(root), "--area", "project", success=False)
    assert "key contracts" in result["error"]


def test_generated_sql_policy_runs_before_local_acceptance(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    snapshot = root / "project/project-snapshot"
    catalog_path = snapshot / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    dataset = {
        "name": "generated_code",
        "canonical_key": ["modeled_entity_schema_name", "generated_code_name"],
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
                "required": [
                    "generated_code_name",
                    "artifact_type",
                    "generated_code_content",
                ],
            }
        )
    )
    fixtures.write_snapshot_manifest(
        snapshot, kind="project", snapshot_id=str(uuid4()), project_revision=8
    )
    pending = root / "project-change-set"
    pending.mkdir()
    for sql, rule in (
        ("SELECT * FROM bronze.Customer", "code.projection"),
        ("DELETE FROM silver.Customer", "code.statements"),
    ):
        (pending / "generated_code.json").write_text(
            json.dumps(
                [
                    {
                        "modeled_entity_schema_name": "silver",
                        "generated_code_name": "Customer",
                        "artifact_type": "sql_file",
                        "generated_code_status": "active",
                        "generated_code_content": sql,
                    }
                ]
            )
        )
        result = run("validate", "--session", str(root), "--area", "project")
        assert not result["valid"]
        assert any(issue["code"] == rule for issue in result["issues"])
        run(
            "accept",
            "--session",
            str(root),
            "--area",
            "project",
            "--digest",
            result["digest"],
            "--backend-profile",
            "local",
            "--endpoint-sha256",
            "a" * 64,
            success=False,
        )


def test_schema_qualified_entities_remain_distinct_in_overlay(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    snapshot = root / "project/project-snapshot"
    catalog_path = snapshot / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    entity = next(
        item for item in catalog["sections"][0]["datasets"] if item["name"] == "logical_entity"
    )
    records = [
        {
            "logical_entity_schema_name": schema,
            "logical_entity_name": "Customer",
            "logical_entity_status": "active",
        }
        for schema in ("silver_a", "silver_b")
    ]
    entity["row_count"] = len(records)
    catalog_path.write_text(json.dumps(catalog))
    (snapshot / entity["rows_file"]).write_text(
        "".join(json.dumps(item) + "\n" for item in records)
    )
    fixtures.write_snapshot_manifest(
        snapshot, kind="project", snapshot_id="snapshot-project-01", project_revision=8
    )
    pending = root / "project-change-set"
    pending.mkdir()
    (pending / "logical_entity.json").write_text(
        json.dumps([{**records[0], "logical_entity_status": "inactive"}])
    )
    selected = run(
        "select",
        "--session",
        str(root),
        "--area",
        "project",
        "--dataset",
        "logical_entity",
        "--view",
        "effective",
    )
    assert {
        (item["logical_entity_schema_name"], item["logical_entity_status"])
        for item in selected["records"]
    } == {("silver_a", "inactive"), ("silver_b", "active")}


def test_analysis_inferred_cardinality_uses_published_schema_and_preserves_measurements(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    metadata = root / "metadata/metadata-snapshot"
    objects = [
        {**json.loads(line), "zone_code": "source"}
        for line in (metadata / "data/source_object.jsonl").read_text().splitlines()
    ]
    (metadata / "data/source_object.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in objects)
    )
    attributes = [{**record, "attribute_name": "CustomerID"} for record in objects]
    (metadata / "data/source_attribute.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in attributes)
    )
    metadata_catalog = json.loads((metadata / "catalog.json").read_text())
    metadata_catalog["sections"][0]["datasets"][0]["record_type"] = "object"
    metadata_catalog["sections"][0]["datasets"][1]["record_type"] = "attribute"
    metadata_catalog["sections"][0]["datasets"][1]["row_count"] = len(attributes)
    (metadata / "catalog.json").write_text(json.dumps(metadata_catalog))
    fixtures.write_snapshot_manifest(metadata, kind="metadata", snapshot_id="metadata-analysis")

    snapshot = root / "project/project-snapshot"
    catalog = json.loads((snapshot / "catalog.json").read_text())
    for name, rows in (("project_input_scope", objects), ("analysis_result", [])):
        definition = DATASETS_BY_NAME[name]
        catalog["sections"].append(
            {
                "name": definition.section,
                "datasets": [
                    {
                        "name": name,
                        "canonical_key": list(definition.canonical_key),
                        "row_count": len(rows),
                        "rows_file": f"data/{name}.jsonl",
                        "schema_file": f"schemas/{name}.schema.json",
                    }
                ],
            }
        )
        (snapshot / f"data/{name}.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in rows)
        )
        (snapshot / f"schemas/{name}.schema.json").write_text(
            json.dumps(build_project_dataset_schema(definition))
        )
    (snapshot / "catalog.json").write_text(json.dumps(catalog))
    fixtures.write_snapshot_manifest(
        snapshot, kind="project", snapshot_id="project-analysis", project_revision=8
    )
    record = AnalysisResultRecord.model_validate(
        {
            **{
                f"from_{field}": attributes[1][field]
                for field in (
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                    "attribute_name",
                )
            },
            **{
                f"to_{field}": attributes[0][field]
                for field in (
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                    "attribute_name",
                )
            },
            "relationship_kind": "reference",
            "relationship_basis": "Orders reference customers; cardinality is inferred separately.",
            "analysis_result_status": "active",
            "analysis_result_is_locked": False,
        }
    ).model_dump(mode="json")
    assert record["inferred_cardinality"] == "unknown"
    pending = root / "project-change-set"
    pending.mkdir()
    path = pending / "analysis_result.json"
    for cardinality in (
        "one_to_one",
        "one_to_many",
        "many_to_one",
        "many_to_many",
        "unknown",
    ):
        record["inferred_cardinality"] = cardinality
        path.write_text(json.dumps([record]))
        result = run("validate", "--session", str(root), "--area", "project")
        assert result["valid"], result["issues"]

    record.update(
        {
            "inferred_cardinality": "one_to_one",
            "validation_policy_version": "1.0.0",
            "validation_result": "supported",
            "validation_source_non_null_count": 10,
            "validation_source_distinct_count": 3,
            "validation_target_non_null_count": 4,
            "validation_target_distinct_count": 4,
            "validation_source_missing_target_count": 0,
            "validation_unused_target_count": 1,
            "validation_duplicate_target_key_count": 0,
        }
    )
    path.write_text(json.dumps([record]))
    result = run("validate", "--session", str(root), "--area", "project")
    assert result["valid"], result["issues"]
    assert any(
        issue["code"] == "analysis_inferred_cardinality_mismatch" and issue["severity"] == "warning"
        for issue in result["issues"]
    )
    assert json.loads(path.read_text()) == [record]

    for invalid in (None, "many", 1):
        path.write_text(json.dumps([{**record, "inferred_cardinality": invalid}]))
        result = run("validate", "--session", str(root), "--area", "project")
        assert not result["valid"]
        assert any(issue["code"] == "schema" for issue in result["issues"])


def test_legacy_project_catalog_is_rejected_before_selection(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    snapshot = root / "project/project-snapshot"
    catalog_path = snapshot / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    entity = next(
        item for item in catalog["sections"][0]["datasets"] if item["name"] == "logical_entity"
    )
    entity["canonical_key"] = ["logical_entity_name"]
    catalog_path.write_text(json.dumps(catalog))
    fixtures.write_snapshot_manifest(
        snapshot, kind="project", snapshot_id="project-snapshot-01", project_revision=8
    )
    result = run(
        "select",
        "--session",
        str(root),
        "--area",
        "project",
        "--dataset",
        "logical_entity",
        success=False,
    )
    assert "Legacy Project Snapshot" in result["error"]


def test_retired_mapping_dependency_catalog_is_rejected_before_selection(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    snapshot = root / "project/project-snapshot"
    catalog_path = snapshot / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    catalog["sections"].append(
        {
            "name": "mapping",
            "datasets": [
                {
                    "name": "mapping_dependency",
                    "canonical_key": ["modeled_entity_type", "source_system_code"],
                }
            ],
        }
    )
    catalog_path.write_text(json.dumps(catalog))
    fixtures.write_snapshot_manifest(
        snapshot, kind="project", snapshot_id="project-snapshot-01", project_revision=8
    )
    result = run(
        "select",
        "--session",
        str(root),
        "--area",
        "project",
        "--dataset",
        "logical_entity",
        success=False,
    )
    assert "Legacy Project Snapshot" in result["error"]


def test_context_uuid_is_created_once_and_published_schema_rejects_legacy_fields(
    tmp_path: Path,
) -> None:
    from uuid import UUID

    root = workspace(tmp_path)
    snapshot = root / "project/project-snapshot"
    catalog = json.loads((snapshot / "catalog.json").read_text())
    for name, rows in (
        (
            "context_type",
            [
                {
                    "context_type_name": "Business Requirement",
                    "context_type_description": None,
                }
            ],
        ),
        ("context_group", []),
        ("context_record", []),
    ):
        definition = DATASETS_BY_NAME[name]
        catalog["sections"].append(
            {
                "name": "context",
                "datasets": [
                    {
                        "name": name,
                        "record_type": name,
                        "canonical_key": list(definition.canonical_key),
                        "row_count": len(rows),
                        "rows_file": f"data/{name}.jsonl",
                        "schema_file": f"schemas/{name}.schema.json",
                    }
                ],
            }
        )
        (snapshot / f"data/{name}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows)
        )
        (snapshot / f"schemas/{name}.schema.json").write_text(
            json.dumps(build_project_dataset_schema(definition))
        )
    (snapshot / "catalog.json").write_text(json.dumps(catalog))
    fixtures.write_snapshot_manifest(
        snapshot, kind="project", snapshot_id="context-fixture", project_revision=8
    )
    args = ("--session", str(root), "--area", "project")
    group = {
        "context_group_name": "Identity",
        "context_type_name": "Business Requirement",
        "context_group_description": None,
        "source_system_code": None,
        "is_active": True,
    }
    first = run(
        "upsert",
        *args,
        "--dataset",
        "context_group",
        "--record",
        json.dumps(group),
        "--expected-digest",
        "empty",
    )
    record = {
        "context_group_name": "Identity",
        "context_text": "Customer numbers preserve leading zeros.",
        "source_reference": "Requirements §2",
        "status": "active",
        "is_locked": False,
    }
    created = run(
        "upsert",
        *args,
        "--dataset",
        "context_record",
        "--record",
        json.dumps(record),
        "--expected-digest",
        first["digest"],
    )
    record_id = created["context_record_id"]
    assert str(UUID(record_id)) == record_id
    pending = root / "project-change-set/context_record.json"
    saved = json.loads(pending.read_text())
    assert len(saved) == 1 and saved[0] == {**record, "context_record_id": record_id}
    before = pending.read_bytes()
    run(
        "upsert",
        *args,
        "--dataset",
        "context_record",
        "--record",
        json.dumps(record),
        "--expected-digest",
        first["digest"],
        success=False,
    )
    assert pending.read_bytes() == before
    record.update(
        context_record_id=record_id,
        context_text="Customer numbers retain leading zeros after import.",
    )
    edited = run(
        "upsert",
        *args,
        "--dataset",
        "context_record",
        "--record",
        json.dumps(record),
        "--expected-digest",
        created["digest"],
    )
    assert edited["context_record_id"] == record_id
    assert json.loads(pending.read_text()) == [record]
    for invalid in (
        {**record, "context_record_id": "human-entered-key"},
        {**record, "record_key": "identity"},
        {**record, "source_reference": {"section": "2"}},
        {**record, "source_reference": "é" * 32769},
    ):
        run(
            "upsert",
            *args,
            "--dataset",
            "context_record",
            "--record",
            json.dumps(invalid),
            "--expected-digest",
            edited["digest"],
            success=False,
        )
        assert json.loads(pending.read_text()) == [record]
    rejected = run(
        "upsert",
        *args,
        "--dataset",
        "context_type",
        "--record",
        json.dumps({"context_type_name": "New type", "context_type_description": None}),
        "--expected-digest",
        edited["digest"],
        success=False,
    )
    assert "read-only" in rejected["error"].lower() or "eligible" in rejected["error"].lower()


def test_context_group_locks_and_active_supports_are_checked_locally(
    tmp_path: Path,
) -> None:
    from copy import deepcopy

    from tests.mcp.project_test_fixtures import (
        complete_project_graph,
        snapshot_from_graph,
    )

    root = workspace(tmp_path)
    snapshot = root / "project/project-snapshot"
    graph: dict[str, list[dict[str, object]]] = {
        name: rows for name, rows in complete_project_graph().items()
    }
    graph["context_type"] = [
        record.model_dump(mode="json")
        for record in snapshot_from_graph(complete_project_graph()).context.types
    ]
    graph["context_record"][0]["is_locked"] = True
    datasets: list[dict[str, Any]] = []
    for name, definition in DATASETS_BY_NAME.items():
        rows = graph.get(name, [])
        datasets.append(
            {
                "name": name,
                "record_type": name,
                "canonical_key": list(definition.canonical_key),
                "row_count": len(rows),
                "rows_file": f"data/{name}.jsonl",
                "schema_file": f"schemas/{name}.schema.json",
            }
        )
        (snapshot / f"data/{name}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows)
        )
        (snapshot / f"schemas/{name}.schema.json").write_text(
            json.dumps(build_project_dataset_schema(definition))
        )
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "project",
                "sections": [{"name": "project", "datasets": datasets}],
            }
        )
    )
    fixtures.write_snapshot_manifest(
        snapshot, kind="project", snapshot_id="context-locks", project_revision=8
    )
    pending = root / "project-change-set"
    pending.mkdir()
    group = deepcopy(graph["context_group"][0])
    group["is_active"] = False
    (pending / "context_group.json").write_text(json.dumps([group]))
    result = run("validate", "--session", str(root), "--area", "project")
    codes = {issue["code"] for issue in result["issues"]}
    assert "context_group_child_locked" in codes
    assert "active_dependency_invalid" in codes


def test_local_digest_orders_change_set_files_ordinally(tmp_path: Path) -> None:
    """Node, PowerShell and Stage Runner must hash copy.json before copy_group.json."""
    root = workspace(tmp_path)
    snapshot = root / "metadata" / "metadata-snapshot"
    catalog = json.loads((snapshot / "catalog.json").read_text())
    for name in ("copy", "copy_group"):
        key = ["tenant_code", "system_code", f"{name}_name"]
        catalog["sections"][0]["datasets"].append(
            {
                "name": name,
                "record_type": name,
                "row_count": 0,
                "canonical_key": key,
                "rows_file": f"data/{name}.jsonl",
                "schema_file": f"schemas/{name}.schema.json",
            }
        )
        (snapshot / "data" / f"{name}.jsonl").write_text("")
        fields = {field: {"type": "string"} for field in key}
        (snapshot / "schemas" / f"{name}.schema.json").write_text(
            json.dumps(
                {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": fields,
                    "required": key,
                    "x-gds-change-set-eligible": True,
                    "x-gds-canonical-key": key,
                    "x-gds-references": [],
                }
            )
        )
    (snapshot / "catalog.json").write_text(json.dumps(catalog))
    fixtures.write_snapshot_manifest(snapshot, kind="metadata", snapshot_id="snapshot-01")
    changes = root / "metadata-change-set"
    changes.mkdir(exist_ok=True)
    for name in ("copy_group", "copy"):
        record = {"tenant_code": "TENANT_A", "system_code": "CRM", f"{name}_name": "MAIN"}
        (changes / f"{name}.json").write_text(json.dumps([record]), encoding="utf-8")

    reviewed = run("review", "--session", str(root), "--area", "metadata")

    expected = hashlib.sha256()
    # Python sorts ASCII names by code point, which equals .NET StringComparer.Ordinal.
    for name in sorted(path.name for path in changes.iterdir()):
        content = (changes / name).read_bytes()
        expected.update(f"{name}\0{len(content)}\0".encode())
        expected.update(content)
    assert sorted(path.name for path in changes.iterdir()) == ["copy.json", "copy_group.json"]
    assert reviewed["digest"] == expected.hexdigest()


def _workspace_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_next_drives_metadata_submission_one_action_at_a_time(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    started = run("next", "--session", str(fresh))
    assert (started["state"], started["action"]["command"]) == ("no_session", "session-init")

    root = workspace(tmp_path)
    meta = ["--session", str(root), "--area", "metadata"]
    assert run("next", *meta)["state"] == "no_pending_changes"
    copied = run(
        "copy",
        *meta,
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"CRM"}',
        "--expected-digest",
        "empty",
    )
    step = run("next", *meta)
    assert step["state"] == "needs_validation"
    assert step["action"]["argv"] == ["validate", *meta]
    assert step["facts"]["pending_datasets"] == {"source_object": 1}
    before = _workspace_hashes(root)
    assert run("next", *meta) == step
    assert _workspace_hashes(root) == before  # next never writes.
    run(*step["action"]["argv"])

    step = run("next", *meta)
    assert step["state"] == "ready_for_review"
    assert step["action"]["kind"] == "ask_user"
    plan = step["action"]["after_approval"]
    assert [item.get("tool", item.get("command")) for item in plan] == [
        "atlas_checkStageRunner",
        "check_tenant_lock",
        "create_metadata_change_set",
        "accept",
        "atlas_stageApprovedManifest",
    ]
    assert plan[2]["arguments"] == {"tenant_id": 1}
    accept = plan[3]["argv"]
    assert accept[accept.index("--digest") + 1] == copied["digest"]

    # The agent saves the extension and MCP results exactly where next asked.
    Path(plan[0]["input"]["outputFile"]).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": "ready",
                "backend": {"profile": "local", "endpoint_sha256": "a" * 64},
            }
        )
    )
    change_set_id = str(uuid4())
    Path(plan[2]["save_response_to"]).write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "tenant_id": 1,
                "metadata_change_set_id": change_set_id,
                "created": True,
                "status": "active",
                "draft_revision": 1,
            }
        )
    )
    prepared = run(*accept)
    step = run("next", *meta)
    assert step["state"] == "stage_prepared"
    assert step["action"] == {
        "kind": "extension",
        "tool": "atlas_stageApprovedManifest",
        "input": {"manifestPath": prepared["stage_manifest_path"]},
    }

    # Simulate the Stage Runner's verified receipt (tested in the extension suite).
    evidence = root / ".atlas/tasks" / f"{prepared['task_id']}.evidence"
    operation_path = evidence / f"{prepared['operation_id']}.json"
    operation = json.loads(operation_path.read_text())
    operation["stage_attempt"] = {"status": "verified"}
    operation["stage"] = {
        "fingerprint_verified": True,
        "accepted_digest": operation["local_digest"],
        "status": "staged",
        "change_set_id": change_set_id,
        "draft_revision": 2,
        "stage_fingerprint": "c" * 64,
    }
    operation["draft"]["revision"] = 2
    operation_path.write_text(json.dumps(operation))
    step = run("next", *meta)
    assert step["state"] == "staged"
    assert (step["action"]["tool"], step["action"]["arguments"]) == (
        "validate_metadata_change_set",
        {"tenant_id": 1, "metadata_change_set_id": change_set_id, "expected_draft_revision": 2},
    )
    server = {
        "schema_version": "1.0",
        "tenant_id": 1,
        "metadata_change_set_id": change_set_id,
        "draft_revision": 2,
        "valid": True,
        "status": "validated",
        "candidate_digest": "b" * 64,
        "error_count": 0,
        "action_review": [],
    }
    Path(step["action"]["save_response_to"]).write_text(json.dumps(server))
    run(
        "operation-record",
        *meta,
        "--checkpoint",
        "validation",
        "--file",
        step["action"]["save_response_to"],
    )

    step = run("next", *meta)
    assert step["state"] == "server_validated"
    assert step["action"]["question"].startswith("Apply these validated changes")
    run(*step["action"]["after_approval"][0]["argv"])

    step = run("next", *meta)
    assert step["state"] == "apply_approved"
    assert step["action"]["tool"] == "apply_metadata_change_set"
    assert step["action"]["arguments"]["expected_candidate_digest"] == "b" * 64

    # Apply was refused because the candidate changed: validate again and ask again.
    step = run("next", *meta, "--error", "candidate_digest_conflict")
    assert (step["state"], step["action"]["tool"]) == (
        "error_recovery",
        "validate_metadata_change_set",
    )
    assert step["action"]["arguments"]["expected_draft_revision"] == 2
    server = {**server, "candidate_digest": "c" * 64}
    Path(step["action"]["save_response_to"]).write_text(json.dumps(server))
    run(
        "operation-record",
        *meta,
        "--checkpoint",
        "validation",
        "--file",
        step["action"]["save_response_to"],
    )
    step = run("next", *meta)
    assert step["state"] == "server_validated"  # The old approval bound the old review.
    run(*step["action"]["after_approval"][0]["argv"])
    step = run("next", *meta)
    assert step["state"] == "apply_approved"
    assert step["action"]["arguments"]["expected_candidate_digest"] == "c" * 64
    Path(step["action"]["save_response_to"]).write_text(
        json.dumps({**server, "applied": True, "status": "applied", "action_count": 1})
    )
    run(
        "operation-record",
        *meta,
        "--checkpoint",
        "apply",
        "--file",
        step["action"]["save_response_to"],
    )

    step = run("next", *meta)
    assert step["state"] == "refresh_required"
    assert (step["action"]["tool"], step["action"]["arguments"]) == (
        "create_metadata_snapshot",
        {"tenant_id": 1},
    )


def test_next_recovers_an_uncertain_stage_before_anything_else(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    meta = ["--session", str(root), "--area", "metadata"]
    copied = run(
        "copy", *meta, "--dataset", "source_object", "--where", "{}", "--expected-digest", "empty"
    )
    accepted = run(
        "accept",
        *meta,
        "--digest",
        copied["digest"],
        "--backend-profile",
        "local",
        "--endpoint-sha256",
        "a" * 64,
    )
    run("draft-cache", *meta, "--id", str(uuid4()), "--revision", "1", "--status", "active")
    prepared = run("prepare-stage-request", *meta)
    operation_path = root / accepted["path"]
    operation = json.loads(operation_path.read_text())
    operation["stage_attempt"] = {"status": "unknown"}
    operation_path.write_text(json.dumps(operation))
    run(
        "copy",
        *meta,
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"ERP"}',
        "--expected-digest",
        run("review", *meta)["digest"],
    )

    for arguments in (meta, ["--session", str(root)]):
        step = run("next", *arguments)
        assert step["state"] == "stage_uncertain"
        assert step["action"]["input"] == {
            "manifestPath": prepared["stage_manifest_path"],
            "recoverOnly": True,
        }


def test_next_reports_local_validation_errors_and_other_work(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    meta = ["--session", str(root), "--area", "metadata"]
    record = run("select", *meta, "--dataset", "source_object", "--where", "{}")["records"][0]
    broken = {**record, "object_name": "Customer2", "unexpected_field": 1}
    pending = root / "metadata-change-set/source_object.json"
    pending.parent.mkdir(exist_ok=True)
    pending.write_text(json.dumps([broken]))
    run("validate", *meta)
    step = run("next", *meta)
    assert step["state"] == "validation_failed"
    assert step["action"]["kind"] == "author"
    assert step["facts"]["issue_count"] >= 1
    overview = run("next", "--session", str(root))
    assert overview["area"] == "metadata"
    assert overview["state"] == "validation_failed"
    assert run("next", "--session", str(root), "--area", "project")["state"] == "no_pending_changes"


def _review_workspace(tmp_path: Path) -> Path:
    """Workspace with the realistic Snapshots recorded for agent evaluations."""
    fixtures = ROOT / "tests/atlas/eval/fixtures"
    world = json.loads((fixtures / "world.json").read_text(encoding="utf-8"))
    root = tmp_path / "review"
    run(
        "session-init",
        "--root",
        str(root),
        "--tenant",
        world["tenant"]["tenant_code"],
        "--tenant-id",
        str(world["tenant"]["tenant_id"]),
        "--project-id",
        str(world["project"]["project_id"]),
        "--project-name",
        world["project"]["project_name"],
    )
    for area, snapshot in world["snapshots"].items():
        run(
            "snapshot-install",
            "--session",
            str(root),
            "--area",
            area,
            "--archive",
            str(fixtures / snapshot["file"]),
            "--snapshot-id",
            snapshot["snapshot_id"],
            "--size-bytes",
            str(snapshot["size_bytes"]),
            "--sha256",
            snapshot["sha256"],
        )
    run("task-add", "--session", str(root), "--outcome", "Model customer addresses")
    return root


def test_policy_apply_adds_the_web_workflow_technical_columns(tmp_path: Path) -> None:
    root = _review_workspace(tmp_path)
    project = ["--session", str(root), "--area", "project"]
    source = {
        "support_source_type": "object",
        "source_object": {
            "tenant_code": "DEMO_GDS_TENANT",
            "system_code": "DEMO_CUSTOMER_SYSTEM",
            "connection_code": "DEMO_GDS",
            "object_schema": "bronze_demo",
            "object_name": "customer",
        },
        "source_order": 1,
        "rationale": "Customer rows carry their postal address.",
        "status": "active",
        "is_locked": False,
    }
    entity = {
        "logical_entity_schema_name": "silver_demo",
        "logical_entity_name": "CustomerAddress",
        "logical_entity_definition": "A postal address used by a Customer.",
        "logical_entity_type": "core",
        "logical_entity_type_detail": None,
        "logical_entity_grain": "One address per Customer",
        "logical_entity_dependency_order": 1,
        "logical_entity_status": "active",
        "logical_entity_is_locked": False,
        "submodels": [],
        "sources": [source],
    }

    def attribute(name: str, ordinal: int) -> dict[str, Any]:
        return {
            "logical_entity_schema_name": "silver_demo",
            "logical_entity_name": "CustomerAddress",
            "logical_attribute_name": name,
            "logical_attribute_definition": f"{name} of the address.",
            "logical_attribute_data_type": "STRING",
            "logical_attribute_is_nullable": True,
            "logical_attribute_is_natural_key": False,
            "logical_attribute_is_surrogate_key": False,
            "logical_attribute_ordinal_position": ordinal,
            "logical_attribute_is_audit_column": False,
            "logical_attribute_status": "active",
            "logical_attribute_is_locked": False,
            "sources": [],
        }

    changes = {
        "logical_entity": [entity],
        "logical_attribute": [attribute("PostalCode", 5), attribute("AddressLine", 2)],
    }
    digest = run(
        "upsert-batch", *project, "--changes", json.dumps(changes), "--expected-digest", "empty"
    )["digest"]
    apply = ["policy-apply", "--session", str(root), "--layer", "logical"]
    preview = run(*apply, "--expected-digest", digest, "--dry-run", "true")
    assert "silver_demo.CustomerAddress.CustomerAddressID" in preview["added"]
    assert preview["digest"] == digest  # A dry run writes nothing.
    stale = run(*apply, "--expected-digest", "0" * 64, success=False)
    assert "digest conflict" in stale["error"]

    applied = run(*apply, "--expected-digest", digest)
    rows = run(
        "select",
        *project,
        "--dataset",
        "logical_attribute",
        "--where",
        json.dumps({"logical_entity_name": "CustomerAddress"}),
        "--view",
        "effective",
    )["records"]
    ordered = sorted(rows, key=lambda row: row["logical_attribute_ordinal_position"])
    names = [row["logical_attribute_name"] for row in ordered]
    assert names[:4] == ["CustomerAddressID", "AddressLine", "PostalCode", "SourceSystemID"]
    assert names[-1] == "UpdatedBy" and len(names) == 13
    surrogate = ordered[0]
    assert surrogate["logical_attribute_is_surrogate_key"] is True
    assert (
        surrogate["logical_attribute_data_type"],
        surrogate["logical_attribute_is_nullable"],
    ) == (
        "BIGINT",
        False,
    )
    assert all(row["logical_attribute_is_audit_column"] for row in ordered[3:])
    report = run("validate", *project)
    policy = {
        "project.own-surrogate",
        "project.audit-order",
        "project.audit-role",
        "project.audit-template",
    }
    assert not [issue for issue in report["issues"] if issue["code"] in policy]

    again = run(*apply, "--expected-digest", applied["digest"])
    assert (again["added"], again["changed"]) == ([], [])
    assert again["digest"] == applied["digest"]


def test_coverage_uses_the_web_workflow_rule_on_the_effective_project(tmp_path: Path) -> None:
    root = _review_workspace(tmp_path)
    logical = ["coverage", "--session", str(root), "--layer", "logical"]
    assert run(*logical)["meets_target"] is True
    project = ["--session", str(root), "--area", "project"]
    customer = run(
        "select",
        *project,
        "--dataset",
        "logical_entity",
        "--where",
        json.dumps({"logical_entity_name": "Customer"}),
    )["records"][0]
    customer["sources"] = []  # The pending draft drops Customer's only Object source.
    run(
        "upsert",
        *project,
        "--dataset",
        "logical_entity",
        "--record",
        json.dumps(customer),
        "--expected-digest",
        "empty",
    )
    report = run(*logical)
    assert (report["total"], report["covered"], report["required"]) == (2, 1, 2)
    assert report["meets_target"] is False and report["enforced"] is False
    assert report["missing"] == [
        "DEMO_GDS_TENANT.DEMO_CUSTOMER_SYSTEM.DEMO_GDS.bronze_demo.customer"
    ]
    order = {
        "tenant_code": "DEMO_GDS_TENANT",
        "system_code": "DEMO_CUSTOMER_SYSTEM",
        "connection_code": "DEMO_GDS",
        "object_schema": "bronze_demo",
        "object_name": "orders",
    }
    narrowed = run(*logical, "--select", json.dumps([order]))
    assert (narrowed["total"], narrowed["covered"], narrowed["meets_target"]) == (1, 1, True)
    outside = run(
        *logical, "--select", json.dumps([{**order, "object_name": "unknown"}]), success=False
    )
    assert "outside" in outside["error"]
    dimensional = run("coverage", "--session", str(root), "--layer", "dimensional")
    assert (dimensional["threshold_percent"], dimensional["meets_target"]) == (60, True)


def test_web_managed_project_datasets_stay_read_only_in_atlas(tmp_path: Path) -> None:
    root = _review_workspace(tmp_path)
    project = ["--session", str(root), "--area", "project"]
    scope = run("select", *project, "--dataset", "project_input_scope", "--limit", "1")["records"][
        0
    ]
    for dataset in ("project_input_scope", "profiling_profile"):
        for command, payload in (
            ("upsert", ["--dataset", dataset, "--record", json.dumps(scope)]),
            ("upsert-batch", ["--changes", json.dumps({dataset: [scope]})]),
            ("copy", ["--dataset", dataset, "--where", "{}"]),
        ):
            refused = run(command, *project, *payload, "--expected-digest", "empty", success=False)
            assert "is managed outside Atlas" in refused["error"], (command, dataset)
    assert not (root / "project-change-set").exists() or not any(
        (root / "project-change-set").iterdir()
    )

    # A draft from an older workspace or a manual edit blocks acceptance but can be discarded.
    pending = root / "project-change-set"
    pending.mkdir(exist_ok=True)
    (pending / "project_input_scope.json").write_text(json.dumps([scope]))
    result = run("validate", *project)
    assert not result["valid"]
    assert {
        (issue["dataset"], issue["severity"])
        for issue in result["issues"]
        if issue["code"] == "web_managed_dataset"
    } == {("project_input_scope", "error")}
    run(
        "accept",
        *project,
        "--digest",
        result["digest"],
        "--backend-profile",
        "local",
        "--endpoint-sha256",
        "a" * 64,
        success=False,
    )
    key = {
        field: scope[field]
        for field in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        )
    }
    run(
        "discard",
        *project,
        "--dataset",
        "project_input_scope",
        "--key",
        json.dumps(key),
        "--expected-digest",
        result["digest"],
    )
    assert not any(
        issue["code"] == "web_managed_dataset" for issue in run("validate", *project)["issues"]
    )


def test_next_error_returns_one_recovery_action_per_server_code(tmp_path: Path) -> None:
    root = _review_workspace(tmp_path)
    tenant_id = json.loads((root / ".atlas/session.json").read_text())["tenant"]["id"]
    project = ["--session", str(root), "--area", "project"]
    assert (
        "--error requires --area"
        in run("next", "--session", str(root), "--error", "tenant_lock_required", success=False)[
            "error"
        ]
    )
    assert (
        "server error code" in run("next", *project, "--error", "Bad Code", success=False)["error"]
    )

    lock = run("next", *project, "--error", "tenant_lock_required")
    assert (lock["state"], lock["facts"]) == (
        "error_recovery",
        {"error_code": "tenant_lock_required"},
    )
    assert (lock["action"]["tool"], lock["action"]["arguments"]) == (
        "check_tenant_lock",
        {"tenant_id": tenant_id},
    )
    assert "override_tenant_lock" in lock["then"][1]

    stage = run("next", *project, "--error", "stage_runner_required")
    assert stage["action"]["argv"] == ["next", *project]

    expected_kinds = {
        "tenant_locked": "ask_user",
        "project_locked": "stop",
        "authorization_denied": "stop",
        "object_locked": "author",
        "internal_error": "stop",
        "something_new": "stop",
        # No bound operation yet, so there is no draft to validate or inspect.
        "candidate_digest_conflict": "stop",
        "project_change_set_not_active": "stop",
    }
    for code, kind in expected_kinds.items():
        step = run("next", *project, "--error", code)
        assert (step["state"], step["action"]["kind"]) == ("error_recovery", kind), code
    assert (
        run("next", *project, "--error", "something_new")["summary"]
        == "Unrecognized server error something_new."
    )
    before = _workspace_hashes(root)
    run("next", *project, "--error", "tenant_lock_required")
    assert _workspace_hashes(root) == before  # Recovery advice never writes.
