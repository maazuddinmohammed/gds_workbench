from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPOSITORY_ROOT / "plugins" / "v2" / "gds" / "scripts" / "gds-local.js"


def run_helper(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(HELPER), *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def write_snapshot_manifest(
    snapshot: Path,
    *,
    kind: str,
    snapshot_id: str,
    model_revision: int | None = None,
    tenant_code: str = "TENANT_A",
    model_id: int = 41,
    model_name: str = "Customer Model",
) -> None:
    catalog_path = snapshot / "catalog.json"
    catalog_document = json.loads(catalog_path.read_text())
    if kind == "model":
        catalog_document["model"] = {
            "model_id": model_id,
            "model_name": model_name,
            "model_revision": model_revision,
        }
        catalog_path.write_text(json.dumps(catalog_document))
    members = []
    for file in sorted(path for path in snapshot.rglob("*") if path.is_file()):
        if file.name == "manifest.json" and file.parent == snapshot:
            continue
        content = file.read_bytes()
        members.append(
            {
                "path": file.relative_to(snapshot).as_posix(),
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    catalog = next(member for member in members if member["path"] == "catalog.json")
    manifest = {
        "snapshot_kind": kind,
        "snapshot_id": snapshot_id,
        "catalog": {"path": "catalog.json", "sha256": catalog["sha256"]},
        "members": members,
    }
    if model_revision is not None:
        manifest["model_revision"] = model_revision
    if kind == "model":
        manifest.update(model_id=model_id, model_name=model_name)
    else:
        manifest["tenant_code"] = tenant_code
    (snapshot / "manifest.json").write_text(json.dumps(manifest))


def test_session_init_allocates_compact_monotonic_sessions(tmp_path: Path) -> None:
    first = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    second = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert json.loads(first.stdout) == {
        "tenant": "TENANT_A",
        "session": "01",
        "path": str(tmp_path / "GDS" / "TENANT_A" / "01"),
    }
    assert json.loads(second.stdout)["session"] == "02"

    tenant_root = tmp_path / "GDS" / "TENANT_A"
    assert json.loads((tenant_root / "manifest.json").read_text()) == {
        "current": "02",
        "highest": 2,
    }
    assert json.loads((tenant_root / "01" / "session.json").read_text()) == {
        "current": None,
        "tasks": [],
    }
    assert sorted(path.name for path in (tenant_root / "01").iterdir()) == [
        "code",
        "metadata",
        "metadata-change-set",
        "model",
        "model-change-set",
        "session.json",
        "tasks",
    ]


def test_session_init_rejects_unsafe_tenant_code(tmp_path: Path) -> None:
    result = run_helper("session-init", "--root", str(tmp_path), "--tenant", "../OTHER")

    assert result.returncode != 0
    assert "Tenant Code" in result.stderr
    assert not (tmp_path / "GDS").exists()


def test_status_summarizes_session_in_one_call_without_snapshot_rows(
    tmp_path: Path,
) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])

    result = run_helper("status", "--session", str(session))

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["current"] is None
    assert output["tasks"] == []
    assert output["cs"] == {}
    assert output["stale"] == []
    assert output["model"] is None
    assert output["snapshots"] == {"metadata": None, "model": None}
    assert output["pending"]["metadata"][0:2] == [0, 0]
    assert len(output["pending"]["metadata"][2]) == 64


def test_status_returns_the_compact_queue_and_cached_server_draft(
    tmp_path: Path,
) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Build logical",
        "--plan",
        '["Build","Review"]',
    )
    run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "code",
        "--title",
        "Generate SQL",
        "--plan",
        '["Check mapping","Generate"]',
    )
    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["cs"] = {
        "model": [
            "00000000-0000-4000-8000-000000000123",
            3,
            "active",
            "01",
            "0" * 64,
        ]
    }
    state_path.write_text(json.dumps(state) + "\n")

    result = run_helper("status", "--session", str(session))

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["current"] == ["01", "model", "Build logical", "doing"]
    assert output["tasks"] == [
        ["01", "model", "Build logical", "doing"],
        ["02", "code", "Generate SQL", "queued"],
    ]
    assert output["cs"] == {
        "model": [
            "00000000-0000-4000-8000-000000000123",
            3,
            "active",
            "01",
            "0" * 64,
        ]
    }


def test_draft_cache_records_and_clears_the_server_resume_tuple(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Stage Customer",
        "--plan",
        '["Copy","Review"]',
    )
    copied = run_helper(
        "copy",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"CRM"}',
        "--expected-digest",
        "empty",
    )
    digest = json.loads(copied.stdout)["digest"]
    accepted = run_helper(
        "accept",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--digest",
        digest,
    )
    assert accepted.returncode == 0, accepted.stderr
    draft_id = "00000000-0000-4000-8000-000000000123"

    recorded = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "4",
        "--status",
        "validated",
    )

    assert recorded.returncode == 0, recorded.stderr
    assert json.loads(recorded.stdout) == {
        "area": "metadata",
        "draft": [draft_id, 4, "validated", "01", digest],
    }
    assert json.loads(run_helper("status", "--session", str(session)).stdout)["cs"] == {
        "metadata": [draft_id, 4, "validated", "01", digest]
    }

    cleared = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--clear",
        "true",
        "--expected-id",
        draft_id,
        "--expected-revision",
        "4",
    )
    assert cleared.returncode == 0, cleared.stderr
    assert json.loads(cleared.stdout) == {"area": "metadata", "draft": None}
    state = json.loads((session / "session.json").read_text())
    assert "cs" not in state


def write_metadata_snapshot(session: Path) -> None:
    snapshot = session / "metadata" / "metadata-snapshot"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "metadata",
                "sections": [
                    {
                        "name": "operational",
                        "datasets": [
                            {
                                "name": "source_object",
                                "record_type": "source_object",
                                "row_count": 2,
                                "canonical_key": [
                                    "tenant_code",
                                    "system_code",
                                    "connection_code",
                                    "object_schema",
                                    "object_name",
                                ],
                                "rows_file": "data/source_object.jsonl",
                                "schema_file": "schemas/source_object.schema.json",
                            },
                            {
                                "name": "source_attribute",
                                "record_type": "source_attribute",
                                "row_count": 0,
                                "canonical_key": [
                                    "tenant_code",
                                    "system_code",
                                    "connection_code",
                                    "object_schema",
                                    "object_name",
                                    "attribute_name",
                                ],
                                "rows_file": "data/source_attribute.jsonl",
                                "schema_file": "schemas/source_attribute.schema.json",
                            },
                        ],
                    }
                ],
            }
        )
    )
    records = [
        {
            "tenant_code": "TENANT_A",
            "system_code": "CRM",
            "connection_code": "MAIN",
            "object_schema": "sales",
            "object_name": "Customer",
            "is_active": True,
        },
        {
            "tenant_code": "TENANT_A",
            "system_code": "ERP",
            "connection_code": "MAIN",
            "object_schema": "sales",
            "object_name": "Order",
            "is_active": True,
        },
    ]
    (snapshot / "data" / "source_object.jsonl").write_text(
        "".join(f"{json.dumps(record)}\n" for record in records)
    )
    (snapshot / "data" / "source_attribute.jsonl").write_text("")
    fields = {
        name: {"type": field_type}
        for name, field_type in (
            ("tenant_code", "string"),
            ("system_code", "string"),
            ("connection_code", "string"),
            ("object_schema", "string"),
            ("object_name", "string"),
            ("is_active", "boolean"),
        )
    }
    (snapshot / "schemas" / "source_object.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": fields,
                "required": list(fields),
                "x-gds-change-set-eligible": True,
                "x-gds-canonical-key": [
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                ],
                "x-gds-references": [],
            }
        )
    )
    attribute_fields = {
        **fields,
        "attribute_name": {"type": "string"},
    }
    (snapshot / "schemas" / "source_attribute.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": attribute_fields,
                "required": list(attribute_fields),
                "x-gds-change-set-eligible": True,
                "x-gds-canonical-key": [
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                    "attribute_name",
                ],
                "x-gds-references": [
                    {
                        "columns": [
                            "tenant_code",
                            "system_code",
                            "connection_code",
                            "object_schema",
                            "object_name",
                        ],
                        "target_record_type": "source_object",
                        "target_columns": [
                            "tenant_code",
                            "system_code",
                            "connection_code",
                            "object_schema",
                            "object_name",
                        ],
                        "nullable": False,
                    }
                ],
            }
        )
    )
    write_snapshot_manifest(
        snapshot,
        kind="metadata",
        snapshot_id="snapshot-01",
    )


def write_model_snapshot(session: Path) -> None:
    snapshot = session / "model" / "model-snapshot"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    datasets = [
        {
            "name": "model_details",
            "row_count": 1,
            "canonical_key": [],
            "rows_file": "data/model_details.jsonl",
            "schema_file": "schemas/model_details.schema.json",
        },
        {
            "name": "logical_entity",
            "row_count": 0,
            "canonical_key": ["logical_entity_name"],
            "rows_file": "data/logical_entity.jsonl",
            "schema_file": "schemas/logical_entity.schema.json",
        },
        {
            "name": "logical_attribute",
            "row_count": 0,
            "canonical_key": ["logical_entity_name", "logical_attribute_name"],
            "rows_file": "data/logical_attribute.jsonl",
            "schema_file": "schemas/logical_attribute.schema.json",
        },
    ]
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "model",
                "sections": [{"name": "logical", "datasets": datasets}],
            }
        )
    )
    for dataset in datasets:
        rows = (
            '{"model_purpose":"Current purpose"}\n'
            if dataset["name"] == "model_details"
            else ""
        )
        (snapshot / dataset["rows_file"]).write_text(rows)
    (snapshot / "schemas" / "model_details.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"model_purpose": {"type": "string"}},
                "required": ["model_purpose"],
                "x-gds-change-set-eligible": True,
            }
        )
    )
    (snapshot / "schemas" / "logical_entity.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"logical_entity_name": {"type": "string"}},
                "required": ["logical_entity_name"],
                "x-gds-change-set-eligible": True,
            }
        )
    )
    (snapshot / "schemas" / "logical_attribute.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "logical_entity_name": {"type": "string"},
                    "logical_attribute_name": {"type": "string"},
                    "logical_attribute_is_nullable": {"type": "boolean"},
                    "logical_attribute_is_primary_key": {"type": "boolean"},
                    "logical_attribute_is_natural_key": {"type": "boolean"},
                    "logical_attribute_is_surrogate_key": {"type": "boolean"},
                    "sources": {"type": "array", "items": {"type": "object"}},
                },
                "required": [
                    "logical_entity_name",
                    "logical_attribute_name",
                    "logical_attribute_is_nullable",
                    "logical_attribute_is_primary_key",
                    "logical_attribute_is_natural_key",
                    "logical_attribute_is_surrogate_key",
                    "sources",
                ],
                "x-gds-change-set-eligible": True,
            }
        )
    )
    write_snapshot_manifest(
        snapshot,
        kind="model",
        snapshot_id="model-snapshot-01",
        model_revision=8,
    )


def test_model_details_is_change_set_eligible_for_local_edits(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_model_snapshot(session)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Update model purpose",
        "--plan",
        '["Edit","Review"]',
    )
    assert added.returncode == 0, added.stderr

    result = run_helper(
        "upsert",
        "--session",
        str(session),
        "--area",
        "model",
        "--dataset",
        "model_details",
        "--record",
        '{"model_purpose":"Updated purpose"}',
        "--expected-digest",
        "empty",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["action"] == "changed"
    assert json.loads(
        (session / "model-change-set" / "model_details.json").read_text()
    ) == [{"model_purpose": "Updated purpose"}]


def prepare_accepted_metadata_task(tmp_path: Path) -> tuple[Path, str]:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Stage Customer",
        "--plan",
        '["Copy","Review"]',
    )
    assert added.returncode == 0, added.stderr
    copied = run_helper(
        "copy",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"CRM"}',
        "--expected-digest",
        "empty",
    )
    assert copied.returncode == 0, copied.stderr
    digest = json.loads(copied.stdout)["digest"]
    accepted = run_helper(
        "accept",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--digest",
        digest,
    )
    assert accepted.returncode == 0, accepted.stderr
    return session, digest


def test_inspect_returns_catalog_not_snapshot_rows(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)

    result = run_helper("inspect", "--session", str(session), "--area", "metadata")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "area": "metadata",
        "kind": "metadata",
        "id": "snapshot-01",
        "revision": None,
        "datasets": [["source_object", 2], ["source_attribute", 0]],
    }
    assert "Customer" not in result.stdout


def test_first_model_snapshot_binds_session_and_rejects_another_model(
    tmp_path: Path,
) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    snapshot = session / "model" / "model-snapshot"
    snapshot.mkdir()
    (snapshot / "catalog.json").write_text(
        json.dumps({"snapshot_kind": "model", "sections": []})
    )
    write_snapshot_manifest(
        snapshot,
        kind="model",
        snapshot_id="model-snapshot-01",
        model_revision=8,
    )

    first = run_helper("inspect", "--session", str(session), "--area", "model")

    assert first.returncode == 0, first.stderr
    assert json.loads((session / "session.json").read_text())["model"] == [
        41,
        "Customer Model",
    ]
    assert json.loads(run_helper("status", "--session", str(session)).stdout)[
        "model"
    ] == [
        41,
        "Customer Model",
    ]

    write_snapshot_manifest(
        snapshot,
        kind="model",
        snapshot_id="model-snapshot-02",
        model_revision=9,
    )
    same_model = run_helper("inspect", "--session", str(session), "--area", "model")
    assert same_model.returncode == 0, same_model.stderr

    write_snapshot_manifest(
        snapshot,
        kind="model",
        snapshot_id="model-snapshot-03",
        model_revision=1,
        model_id=42,
        model_name="Other Model",
    )
    other_model = run_helper("inspect", "--session", str(session), "--area", "model")
    assert other_model.returncode != 0
    assert "start a new session for Model 42" in other_model.stderr


def test_snapshot_identity_must_match_session_tenant_and_model_catalog(
    tmp_path: Path,
) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    metadata_manifest = session / "metadata" / "metadata-snapshot" / "manifest.json"
    metadata_document = json.loads(metadata_manifest.read_text())
    metadata_document["tenant_code"] = "TENANT_B"
    metadata_manifest.write_text(json.dumps(metadata_document))
    tenant_mismatch = run_helper(
        "inspect", "--session", str(session), "--area", "metadata"
    )
    assert tenant_mismatch.returncode != 0
    assert "Tenant Code does not match" in tenant_mismatch.stderr

    snapshot = session / "model" / "model-snapshot"
    snapshot.mkdir()
    (snapshot / "catalog.json").write_text(
        json.dumps({"snapshot_kind": "model", "sections": []})
    )
    write_snapshot_manifest(
        snapshot,
        kind="model",
        snapshot_id="model-snapshot-01",
        model_revision=8,
    )
    model_manifest = snapshot / "manifest.json"
    model_document = json.loads(model_manifest.read_text())
    model_document["model_name"] = "Wrong Name"
    model_manifest.write_text(json.dumps(model_document))
    model_mismatch = run_helper("inspect", "--session", str(session), "--area", "model")
    assert model_mismatch.returncode != 0
    assert "Model identity does not match" in model_mismatch.stderr


def test_invalid_session_model_binding_is_rejected(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["model"] = [0, ""]
    state_path.write_text(json.dumps(state))

    result = run_helper("status", "--session", str(session))

    assert result.returncode != 0
    assert "invalid shape" in result.stderr


def test_legacy_unbound_server_draft_cache_is_rejected(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["cs"] = {"metadata": ["00000000-0000-4000-8000-000000000123", 1, "active"]}
    state_path.write_text(json.dumps(state) + "\n")

    result = run_helper("status", "--session", str(session))

    assert result.returncode != 0
    assert "invalid shape" in result.stderr


def test_inspect_rejects_duplicate_and_unsafe_manifest_members(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    manifest_path = session / "metadata" / "metadata-snapshot" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    manifest["members"].append(dict(manifest["members"][0]))
    manifest_path.write_text(json.dumps(manifest))
    duplicate = run_helper("inspect", "--session", str(session), "--area", "metadata")
    assert duplicate.returncode != 0
    assert "duplicate member path" in duplicate.stderr

    manifest["members"].pop()
    manifest["members"].append(
        {"path": "../outside.json", "size_bytes": 0, "sha256": "0" * 64}
    )
    manifest_path.write_text(json.dumps(manifest))
    unsafe = run_helper("inspect", "--session", str(session), "--area", "metadata")
    assert unsafe.returncode != 0
    assert "unsafe member path" in unsafe.stderr


def test_inspect_verifies_catalog_size_and_sha256(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    snapshot = session / "metadata" / "metadata-snapshot"
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    catalog_member = next(
        member for member in manifest["members"] if member["path"] == "catalog.json"
    )

    catalog_member["size_bytes"] += 1
    manifest_path.write_text(json.dumps(manifest))
    wrong_size = run_helper("inspect", "--session", str(session), "--area", "metadata")
    assert wrong_size.returncode != 0
    assert "size mismatch" in wrong_size.stderr

    catalog_member["size_bytes"] -= 1
    manifest_path.write_text(json.dumps(manifest))
    catalog_path = snapshot / "catalog.json"
    catalog_path.write_bytes(
        catalog_path.read_bytes().replace(b'"metadata"', b'"metadatz"', 1)
    )
    wrong_hash = run_helper("inspect", "--session", str(session), "--area", "metadata")
    assert wrong_hash.returncode != 0
    assert "SHA-256 mismatch" in wrong_hash.stderr


def test_describe_returns_one_exact_schema_without_rows(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)

    result = run_helper(
        "describe",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["dataset"] == "source_object"
    assert output["count"] == 2
    assert output["canonical_key"] == [
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
    ]
    assert output["schema"]["required"][-1] == "is_active"
    assert "Customer" not in result.stdout


def test_rows_and_schema_are_verified_only_when_accessed(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    snapshot = session / "metadata" / "metadata-snapshot"

    rows = snapshot / "data" / "source_object.jsonl"
    rows.write_bytes(rows.read_bytes().replace(b"Customer", b"CustomeX", 1))
    inspected = run_helper("inspect", "--session", str(session), "--area", "metadata")
    assert inspected.returncode == 0, inspected.stderr
    selected = run_helper(
        "select",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
    )
    assert selected.returncode != 0
    assert "SHA-256 mismatch" in selected.stderr

    manifest = json.loads((snapshot / "manifest.json").read_text())
    rows_member = next(
        member
        for member in manifest["members"]
        if member["path"] == "data/source_object.jsonl"
    )
    rows_member["sha256"] = hashlib.sha256(rows.read_bytes()).hexdigest()
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    schema = snapshot / "schemas" / "source_object.schema.json"
    schema.write_bytes(schema.read_bytes().replace(b'"boolean"', b'"booleaX"', 1))
    described = run_helper(
        "describe",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
    )
    assert described.returncode != 0
    assert "SHA-256 mismatch" in described.stderr


def test_select_returns_only_filtered_compact_batch(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)

    result = run_helper(
        "select",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":" crm "}',
        "--limit",
        "10",
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["dataset"] == "source_object"
    assert output["count"] == 1
    assert output["truncated"] is False
    assert [record["object_name"] for record in output["records"]] == ["Customer"]


def test_select_enforces_a_small_context_limit(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)

    result = run_helper(
        "select",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        "{}",
        "--limit",
        "500",
    )

    assert result.returncode != 0
    assert "between 1 and 200" in result.stderr


def test_task_add_keeps_one_compact_current_task_and_ordered_plans(
    tmp_path: Path,
) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])

    first = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Build logical model",
        "--plan",
        '["Confirm fresh snapshots","Build complete logical coverage","Review"]',
    )
    second = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "code",
        "--title",
        "Generate logical SQL",
        "--plan",
        '["Check mapping readiness","Generate Databricks SQL"]',
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_output = json.loads(first.stdout)
    second_output = json.loads(second.stdout)
    assert first_output["task"] == "01"
    assert first_output["state"] == "doing"
    assert len(first_output["plan_digest"]) == 64
    assert second_output["task"] == "02"
    assert second_output["state"] == "queued"
    assert len(second_output["plan_digest"]) == 64
    assert json.loads((session / "session.json").read_text()) == {
        "current": "01",
        "tasks": [
            ["01", "model", "Build logical model", "doing"],
            ["02", "code", "Generate logical SQL", "queued"],
        ],
    }
    assert json.loads((session / "tasks" / "01.json").read_text()) == [
        "Confirm fresh snapshots",
        "Build complete logical coverage",
        "Review",
    ]


def test_status_returns_current_plan_and_task_plan_update_is_digest_guarded(
    tmp_path: Path,
) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Build logical",
        "--plan",
        '["Inspect scope","Build"]',
    )
    initial_digest = json.loads(added.stdout)["plan_digest"]

    updated = run_helper(
        "task-plan",
        "--session",
        str(session),
        "--task",
        "01",
        "--plan",
        '["Inspect scope","Build","Review"]',
        "--expected-digest",
        initial_digest,
    )

    assert updated.returncode == 0, updated.stderr
    updated_digest = json.loads(updated.stdout)["plan_digest"]
    assert updated_digest != initial_digest
    conflict = run_helper(
        "task-plan",
        "--session",
        str(session),
        "--task",
        "01",
        "--plan",
        '["Overwrite"]',
        "--expected-digest",
        initial_digest,
    )
    assert conflict.returncode != 0
    assert "plan digest conflict" in conflict.stderr

    status = run_helper("status", "--session", str(session))
    output = json.loads(status.stdout)
    assert output["plan"] == ["Inspect scope", "Build", "Review"]
    assert output["plan_digest"] == updated_digest


def test_status_returns_waiting_task_plan_without_mutating_session(
    tmp_path: Path,
) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    plan = ["Inputs: metadata=snapshot-01", "Resume selected metadata work"]
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Waiting metadata task",
        "--plan",
        json.dumps(plan, separators=(",", ":")),
    )
    assert added.returncode == 0, added.stderr
    waiting = run_helper(
        "task-state", "--session", str(session), "--task", "01", "--state", "waiting"
    )
    assert waiting.returncode == 0, waiting.stderr
    state_path = session / "session.json"
    state_before = state_path.read_bytes()

    status = run_helper("status", "--session", str(session))

    assert status.returncode == 0, status.stderr
    output = json.loads(status.stdout)
    assert output["current"] is None
    assert output["resume"] == [
        "01",
        "metadata",
        "Waiting metadata task",
        "waiting",
    ]
    assert output["plan"] == plan
    assert output["plan_digest"] == json.loads(added.stdout)["plan_digest"]
    assert state_path.read_bytes() == state_before


def test_task_state_enforces_gates_and_marks_applied_area_stale(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Build logical model",
        "--plan",
        '["Build","Review","Apply"]',
    )

    invalid = run_helper(
        "task-state", "--session", str(session), "--task", "01", "--state", "applied"
    )
    assert invalid.returncode != 0
    assert "doing -> applied" in invalid.stderr

    for state in ("review", "ready"):
        result = run_helper(
            "task-state",
            "--session",
            str(session),
            "--task",
            "01",
            "--state",
            state,
        )
        assert result.returncode == 0, result.stderr

    pending = b"[]\n"
    filename = "logical_entity.json"
    (session / "model-change-set" / filename).write_bytes(pending)
    digest = hashlib.sha256(
        filename.encode() + b"\0" + str(len(pending)).encode() + b"\0" + pending
    ).hexdigest()
    unaccepted = run_helper(
        "task-state", "--session", str(session), "--task", "01", "--state", "staged"
    )
    assert unaccepted.returncode != 0
    assert "accepted digest" in unaccepted.stderr
    (session / "tasks" / "01.accept.json").write_text(
        json.dumps([digest, "valid", "snapshot-old", 7]) + "\n"
    )
    missing_cache = run_helper(
        "task-state", "--session", str(session), "--task", "01", "--state", "staged"
    )
    assert missing_cache.returncode != 0
    assert "server draft" in missing_cache.stderr
    draft_id = "00000000-0000-4000-8000-000000000123"
    cached = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "model",
        "--id",
        draft_id,
        "--revision",
        "1",
        "--status",
        "active",
    )
    assert cached.returncode == 0, cached.stderr
    staged = run_helper(
        "task-state", "--session", str(session), "--task", "01", "--state", "staged"
    )
    assert staged.returncode == 0, staged.stderr
    validated_cache = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "model",
        "--id",
        draft_id,
        "--revision",
        "2",
        "--status",
        "validated",
    )
    assert validated_cache.returncode == 0, validated_cache.stderr
    applied = run_helper(
        "task-state", "--session", str(session), "--task", "01", "--state", "applied"
    )
    assert applied.returncode == 0, applied.stderr

    state = json.loads((session / "session.json").read_text())
    assert state == {
        "current": None,
        "tasks": [["01", "model", "Build logical model", "applied"]],
        "stale": ["model"],
    }
    assert json.loads((session / "tasks" / "01.applied.json").read_text()) == [
        "model",
        "snapshot-old",
        7,
    ]

    model_snapshot = session / "model" / "model-snapshot"
    model_snapshot.mkdir()
    (model_snapshot / "catalog.json").write_text(
        json.dumps({"snapshot_kind": "model", "sections": []})
    )
    write_snapshot_manifest(
        model_snapshot,
        kind="model",
        snapshot_id="snapshot-new",
        model_revision=8,
    )
    refreshed = run_helper(
        "snapshot-refresh", "--session", str(session), "--area", "model"
    )
    assert refreshed.returncode == 0, refreshed.stderr
    assert json.loads(refreshed.stdout) == {
        "area": "model",
        "id": "snapshot-new",
        "revision": 8,
        "retired": 1,
    }
    assert not (session / "model-change-set" / filename).exists()
    assert "stale" not in json.loads((session / "session.json").read_text())


def prepare_applied_metadata_refresh(
    tmp_path: Path, *, refreshed_active: bool
) -> tuple[Path, Path]:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    pending_record = {
        "tenant_code": "TENANT_A",
        "system_code": "CRM",
        "connection_code": "MAIN",
        "object_schema": "sales",
        "object_name": "Customer",
        "is_active": False,
    }
    pending_path = session / "metadata-change-set" / "source_object.json"
    pending_path.write_text(json.dumps([pending_record]) + "\n")
    (session / "session.json").write_text(
        json.dumps(
            {
                "current": None,
                "tasks": [["01", "metadata", "Update Customer", "applied"]],
                "stale": ["metadata"],
            }
        )
        + "\n"
    )
    (session / "tasks" / "01.applied.json").write_text(
        '["metadata","snapshot-01",null]\n'
    )
    snapshot = session / "metadata" / "metadata-snapshot"
    pending_record["is_active"] = refreshed_active
    order_record = {
        "tenant_code": "TENANT_A",
        "system_code": "ERP",
        "connection_code": "MAIN",
        "object_schema": "sales",
        "object_name": "Order",
        "is_active": True,
    }
    (snapshot / "data" / "source_object.jsonl").write_text(
        f"{json.dumps(pending_record)}\n{json.dumps(order_record)}\n"
    )
    write_snapshot_manifest(snapshot, kind="metadata", snapshot_id="snapshot-02")
    return session, pending_path


def test_snapshot_refresh_retires_exact_applied_files_before_next_task(
    tmp_path: Path,
) -> None:
    session, pending_path = prepare_applied_metadata_refresh(
        tmp_path, refreshed_active=False
    )

    refreshed = run_helper(
        "snapshot-refresh", "--session", str(session), "--area", "metadata"
    )

    assert refreshed.returncode == 0, refreshed.stderr
    assert json.loads(refreshed.stdout)["retired"] == 1
    assert not pending_path.exists()
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Next metadata task",
        "--plan",
        '["Review"]',
    )
    assert added.returncode == 0, added.stderr
    status = json.loads(run_helper("status", "--session", str(session)).stdout)
    assert status["pending"]["metadata"][:2] == [0, 0]


def test_snapshot_refresh_keeps_stale_state_when_applied_records_do_not_match(
    tmp_path: Path,
) -> None:
    session, pending_path = prepare_applied_metadata_refresh(
        tmp_path, refreshed_active=True
    )

    refreshed = run_helper(
        "snapshot-refresh", "--session", str(session), "--area", "metadata"
    )

    assert refreshed.returncode != 0
    assert "does not contain the exact applied local record" in refreshed.stderr
    assert pending_path.exists()
    assert json.loads((session / "session.json").read_text())["stale"] == ["metadata"]


def test_local_change_set_copy_upsert_review_validate_and_discard(
    tmp_path: Path,
) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Update Customer",
        "--plan",
        '["Copy record","Edit locally","Review"]',
    )

    copied = run_helper(
        "copy",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"CRM"}',
        "--expected-digest",
        "empty",
    )
    assert copied.returncode == 0, copied.stderr
    copied_output = json.loads(copied.stdout)
    assert copied_output["count"] == 1
    assert len(copied_output["digest"]) == 64

    customer = {
        "tenant_code": "TENANT_A",
        "system_code": "CRM",
        "connection_code": "MAIN",
        "object_schema": "sales",
        "object_name": "Customer",
        "is_active": False,
    }
    upserted = run_helper(
        "upsert",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--record",
        json.dumps(customer),
        "--expected-digest",
        copied_output["digest"],
    )
    assert upserted.returncode == 0, upserted.stderr
    upserted_output = json.loads(upserted.stdout)
    assert upserted_output["action"] == "changed"

    reviewed = run_helper("review", "--session", str(session), "--area", "metadata")
    assert reviewed.returncode == 0, reviewed.stderr
    review = json.loads(reviewed.stdout)
    assert review["counts"] == {
        "added": 0,
        "changed": 0,
        "reactivated": 0,
        "deactivated": 1,
        "unchanged": 0,
        "total": 1,
    }
    assert review["digest"] == upserted_output["digest"]

    validated = run_helper("validate", "--session", str(session), "--area", "metadata")
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout) == {
        "valid": True,
        "issues": [],
        "digest": review["digest"],
    }

    discarded = run_helper(
        "discard",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--key",
        json.dumps(
            {
                key: customer[key]
                for key in (
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                )
            }
        ),
        "--expected-digest",
        review["digest"],
    )
    assert discarded.returncode == 0, discarded.stderr
    assert json.loads(discarded.stdout)["count"] == 0
    assert (
        json.loads((session / "metadata-change-set" / "source_object.json").read_text())
        == []
    )


def test_upsert_batch_writes_multiple_datasets_in_one_call(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Add Vendor metadata",
        "--plan",
        '["Add Object and Attribute","Review"]',
    )
    assert added.returncode == 0, added.stderr

    vendor = {
        "tenant_code": "TENANT_A",
        "system_code": "CRM",
        "connection_code": "MAIN",
        "object_schema": "sales",
        "object_name": "Vendor",
        "is_active": True,
    }
    changes = {
        "source_object": [vendor],
        "source_attribute": [{**vendor, "attribute_name": "VendorId"}],
    }
    result = run_helper(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--changes",
        json.dumps(changes, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["records"] == 2
    assert output["datasets"] == [
        ["source_attribute", 1, 1],
        ["source_object", 1, 1],
    ]
    assert len(output["digest"]) == 64
    reviewed = json.loads(
        run_helper("review", "--session", str(session), "--area", "metadata").stdout
    )
    assert reviewed["counts"]["added"] == 2
    validated = json.loads(
        run_helper("validate", "--session", str(session), "--area", "metadata").stdout
    )
    assert validated["valid"] is True


def test_upsert_batch_rejects_duplicate_keys_before_writing(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Reject duplicate batch",
        "--plan",
        '["Check batch"]',
    )
    record = {
        "tenant_code": "TENANT_A",
        "system_code": "CRM",
        "connection_code": "MAIN",
        "object_schema": "sales",
        "object_name": "Vendor",
        "is_active": True,
    }

    result = run_helper(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--changes",
        json.dumps({"source_object": [record, record]}, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )

    assert result.returncode != 0
    assert "duplicate canonical key" in result.stderr
    assert list((session / "metadata-change-set").iterdir()) == []

    valid_attribute = {
        **record,
        "attribute_name": "VendorId",
    }
    invalid_later_dataset = run_helper(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--changes",
        json.dumps(
            {
                "source_attribute": [valid_attribute],
                "source_object": [
                    {key: value for key, value in record.items() if key != "is_active"}
                ],
            },
            separators=(",", ":"),
        ),
        "--expected-digest",
        "empty",
    )
    assert invalid_later_dataset.returncode != 0
    assert "source_object batch record 1 is invalid" in invalid_later_dataset.stderr
    assert list((session / "metadata-change-set").iterdir()) == []
    assert json.loads((session / "session.json").read_text())["tasks"][0][3] == "doing"

    too_many = [{**record, "object_name": f"Vendor{index}"} for index in range(201)]
    oversized = run_helper(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--changes",
        json.dumps({"source_object": too_many}, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    assert oversized.returncode != 0
    assert "at most 200 records" in oversized.stderr
    assert list((session / "metadata-change-set").iterdir()) == []


def test_helper_validation_uses_model_graph_and_record_policies(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_model_snapshot(session)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Validate logical key",
        "--plan",
        '["Validate"]',
    )
    assert added.returncode == 0, added.stderr
    (session / "model-change-set" / "logical_attribute.json").write_text(
        json.dumps(
            [
                {
                    "logical_entity_name": "Customer",
                    "logical_attribute_name": "Id",
                    "logical_attribute_is_nullable": True,
                    "logical_attribute_is_primary_key": False,
                    "logical_attribute_is_natural_key": True,
                    "logical_attribute_is_surrogate_key": True,
                    "sources": [],
                }
            ]
        )
    )

    result = run_helper("validate", "--session", str(session), "--area", "model")

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["valid"] is False
    assert "record_policy_invalid" in json.dumps(output["issues"])


def test_upsert_rejects_incomplete_record_and_digest_conflict(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Update Customer",
        "--plan",
        '["Edit locally","Review"]',
    )

    incomplete = run_helper(
        "upsert",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--record",
        '{"object_name":"Customer"}',
        "--expected-digest",
        "empty",
    )
    assert incomplete.returncode != 0
    assert "required" in incomplete.stderr

    conflict = run_helper(
        "copy",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"CRM"}',
        "--expected-digest",
        "0" * 64,
    )
    assert conflict.returncode != 0
    assert "digest conflict" in conflict.stderr


def test_validate_checks_references_on_the_effective_overlay(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Add orphan Attribute",
        "--plan",
        '["Add record","Validate"]',
    )
    orphan = {
        "tenant_code": "TENANT_A",
        "system_code": "CRM",
        "connection_code": "MAIN",
        "object_schema": "sales",
        "object_name": "Missing",
        "attribute_name": "CustomerId",
        "is_active": True,
    }
    upserted = run_helper(
        "upsert",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_attribute",
        "--record",
        json.dumps(orphan),
        "--expected-digest",
        "empty",
    )
    assert upserted.returncode == 0, upserted.stderr

    result = run_helper("validate", "--session", str(session), "--area", "metadata")

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["valid"] is False
    assert any("broken reference" in issue[2] for issue in output["issues"])

    rejected = run_helper(
        "accept",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--digest",
        output["digest"],
    )
    assert rejected.returncode != 0
    assert "validation fails" in rejected.stderr

    overridden = run_helper(
        "accept",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--digest",
        output["digest"],
        "--override",
        "true",
        "--reason",
        "Known temporary parent registration order",
    )
    assert overridden.returncode == 0, overridden.stderr
    assert json.loads(overridden.stdout)["state"] == "overridden"
    assert (
        json.loads((session / "session.json").read_text())["tasks"][0][3]
        == "overridden"
    )
    assert json.loads((session / "tasks" / "01.accept.json").read_text()) == [
        output["digest"],
        "override",
        "Known temporary parent registration order",
        "snapshot-01",
        None,
    ]


def test_acceptance_is_bound_to_exact_change_set_bytes(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Review Customer",
        "--plan",
        '["Copy","Review"]',
    )
    copied = run_helper(
        "copy",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"CRM"}',
        "--expected-digest",
        "empty",
    )
    digest = json.loads(copied.stdout)["digest"]

    accepted = run_helper(
        "accept",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--digest",
        digest,
    )
    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(accepted.stdout)["state"] == "ready"

    pending = session / "metadata-change-set" / "source_object.json"
    pending.write_text(pending.read_text() + " ")
    stale_acceptance = run_helper(
        "accept",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--digest",
        digest,
    )
    assert stale_acceptance.returncode != 0
    assert "digest conflict" in stale_acceptance.stderr


def test_reconcile_classifies_exact_non_overlap_and_conflict_without_writing(
    tmp_path: Path,
) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Stage Customer",
        "--plan",
        '["Copy","Review","Reconcile"]',
    )
    copied = run_helper(
        "copy",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"CRM"}',
        "--expected-digest",
        "empty",
    )
    digest = json.loads(copied.stdout)["digest"]
    accepted = run_helper(
        "accept",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--digest",
        digest,
    )
    assert accepted.returncode == 0, accepted.stderr
    cached = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        "00000000-0000-4000-8000-000000000123",
        "--revision",
        "1",
        "--status",
        "active",
    )
    assert cached.returncode == 0, cached.stderr
    staged = run_helper(
        "task-state", "--session", str(session), "--task", "01", "--state", "staged"
    )
    assert staged.returncode == 0, staged.stderr
    customer = json.loads(
        (session / "metadata-change-set" / "source_object.json").read_text()
    )[0]

    exact = run_helper(
        "reconcile",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--server",
        json.dumps({"source_object": [customer]}),
    )
    assert exact.returncode == 0, exact.stderr
    assert json.loads(exact.stdout)["classification"] == "exact"

    other = {**customer, "system_code": "ERP", "object_name": "Order"}
    non_overlap = run_helper(
        "reconcile",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--server",
        json.dumps({"source_object": [other]}),
    )
    assert non_overlap.returncode == 0, non_overlap.stderr
    assert json.loads(non_overlap.stdout)["classification"] == "non_overlap"

    conflict = run_helper(
        "reconcile",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--server",
        json.dumps({"source_object": [{**customer, "is_active": False}]}),
    )
    assert conflict.returncode == 0, conflict.stderr
    conflict_output = json.loads(conflict.stdout)
    assert conflict_output["classification"] == "conflict"
    assert conflict_output["ready"] is False
    assert conflict_output["conflicts"][0][0] == "source_object"


def test_server_draft_cache_rejects_changed_digest_and_cross_task_reuse(
    tmp_path: Path,
) -> None:
    session, digest = prepare_accepted_metadata_task(tmp_path)
    draft_id = "00000000-0000-4000-8000-000000000123"
    cached = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "2",
        "--status",
        "active",
    )
    assert cached.returncode == 0, cached.stderr
    replaced = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        "00000000-0000-4000-8000-000000000999",
        "--revision",
        "3",
        "--status",
        "active",
    )
    assert replaced.returncode != 0
    assert "immutable" in replaced.stderr
    assert json.loads((session / "session.json").read_text())["cs"]["metadata"] == [
        draft_id,
        2,
        "active",
        "01",
        digest,
    ]
    assert json.loads(cached.stdout)["draft"] == [
        draft_id,
        2,
        "active",
        "01",
        digest,
    ]

    pending = session / "metadata-change-set" / "source_object.json"
    pending.write_text(pending.read_text() + " ")
    changed = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "3",
        "--status",
        "active",
    )
    assert changed.returncode != 0
    assert "accepted digest" in changed.stderr

    pending.write_text(pending.read_text().rstrip() + "\n")
    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["tasks"][0][3] = "waiting"
    state["tasks"].append(["02", "metadata", "Other metadata", "ready"])
    state["current"] = "02"
    (session / "tasks" / "02.json").write_text('["Review"]\n')
    (session / "tasks" / "02.accept.json").write_text(
        json.dumps([digest, "valid", "snapshot-01", None]) + "\n"
    )
    state_path.write_text(json.dumps(state) + "\n")
    cross_task = run_helper(
        "reconcile",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--server",
        '{"source_object":[]}',
    )
    assert cross_task.returncode != 0
    assert "belongs to task 01" in cross_task.stderr


def test_server_draft_cache_advances_digest_only_after_newer_active_stage(
    tmp_path: Path,
) -> None:
    session, first_digest = prepare_accepted_metadata_task(tmp_path)
    draft_id = "00000000-0000-4000-8000-000000000123"
    cached = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "2",
        "--status",
        "active",
    )
    assert cached.returncode == 0, cached.stderr

    pending = session / "metadata-change-set" / "source_object.json"
    pending.write_text(pending.read_text() + " ")
    second_digest = json.loads(
        run_helper("review", "--session", str(session), "--area", "metadata").stdout
    )["digest"]
    assert second_digest != first_digest
    accepted = run_helper(
        "accept",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--digest",
        second_digest,
    )
    assert accepted.returncode == 0, accepted.stderr
    server = {"source_object": json.loads(pending.read_text())}
    before_stage = run_helper(
        "reconcile",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--server",
        json.dumps(server),
    )
    assert before_stage.returncode == 0, before_stage.stderr
    assert json.loads(before_stage.stdout)["cache_bound"] is False

    for revision, status in (("2", "active"), ("3", "validated")):
        rejected = run_helper(
            "draft-cache",
            "--session",
            str(session),
            "--area",
            "metadata",
            "--id",
            draft_id,
            "--revision",
            revision,
            "--status",
            status,
        )
        assert rejected.returncode != 0
        assert "newer active Stage revision" in rejected.stderr

    advanced = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "3",
        "--status",
        "active",
    )
    assert advanced.returncode == 0, advanced.stderr
    assert json.loads(advanced.stdout)["draft"] == [
        draft_id,
        3,
        "active",
        "01",
        second_digest,
    ]
    after_stage = run_helper(
        "reconcile",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--server",
        json.dumps(server),
    )
    assert after_stage.returncode == 0, after_stage.stderr
    assert json.loads(after_stage.stdout)["cache_bound"] is True

    validated = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "3",
        "--status",
        "validated",
    )
    assert validated.returncode == 0, validated.stderr
    regressed = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "3",
        "--status",
        "active",
    )
    assert regressed.returncode != 0
    assert "status cannot regress" in regressed.stderr


def test_task_stash_is_digest_guarded_and_requires_server_cache_clear(
    tmp_path: Path,
) -> None:
    session, digest = prepare_accepted_metadata_task(tmp_path)
    wrong = run_helper(
        "task-stash",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        "0" * 64,
    )
    assert wrong.returncode != 0
    assert "digest conflict" in wrong.stderr
    assert (session / "metadata-change-set" / "source_object.json").exists()
    assert json.loads((session / "session.json").read_text())["current"] == "01"

    cached = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        "00000000-0000-4000-8000-000000000123",
        "--revision",
        "2",
        "--status",
        "active",
    )
    assert cached.returncode == 0, cached.stderr
    blocked = run_helper(
        "task-stash",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        digest,
    )
    assert blocked.returncode != 0
    assert "server draft" in blocked.stderr

    wrong_clear = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--clear",
        "true",
        "--expected-id",
        "00000000-0000-4000-8000-000000000999",
        "--expected-revision",
        "2",
    )
    assert wrong_clear.returncode != 0
    assert "exact cached server draft" in wrong_clear.stderr

    cleared = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--clear",
        "true",
        "--expected-id",
        "00000000-0000-4000-8000-000000000123",
        "--expected-revision",
        "2",
    )
    assert cleared.returncode == 0, cleared.stderr
    stashed = run_helper(
        "task-stash",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        digest,
    )
    assert stashed.returncode == 0, stashed.stderr
    assert json.loads(stashed.stdout) == {
        "task": "01",
        "area": "metadata",
        "digest": digest,
        "files": 1,
    }
    assert list((session / "metadata-change-set").iterdir()) == []
    assert (
        session / "tasks" / "01" / "metadata-change-set" / "source_object.json"
    ).exists()
    assert not (session / "tasks" / "01.accept.json").exists()
    state = json.loads((session / "session.json").read_text())
    assert state["current"] is None
    assert state["tasks"][0][3] == "waiting"
    status = json.loads(run_helper("status", "--session", str(session)).stdout)
    assert status["stashes"] == [["01", "metadata", 1, digest]]


def test_task_stash_rejects_an_empty_live_change_set(tmp_path: Path) -> None:
    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "No pending work",
        "--plan",
        '["Inspect"]',
    )
    assert added.returncode == 0, added.stderr
    empty_digest = json.loads(run_helper("status", "--session", str(session)).stdout)[
        "pending"
    ]["metadata"][2]

    result = run_helper(
        "task-stash",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        empty_digest,
    )
    assert result.returncode != 0
    assert "nothing to stash" in result.stderr


def test_task_restore_isolates_same_area_work_and_requires_fresh_empty_live_set(
    tmp_path: Path,
) -> None:
    session, first_digest = prepare_accepted_metadata_task(tmp_path)
    stashed = run_helper(
        "task-stash",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        first_digest,
    )
    assert stashed.returncode == 0, stashed.stderr

    second = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Other metadata",
        "--plan",
        '["Copy Order"]',
    )
    assert second.returncode == 0, second.stderr
    copied = run_helper(
        "copy",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "source_object",
        "--where",
        '{"system_code":"ERP"}',
        "--expected-digest",
        "empty",
    )
    assert copied.returncode == 0, copied.stderr
    second_digest = json.loads(copied.stdout)["digest"]
    second_stash = run_helper(
        "task-stash",
        "--session",
        str(session),
        "--task",
        "02",
        "--expected-digest",
        second_digest,
    )
    assert second_stash.returncode == 0, second_stash.stderr

    wrong_digest = run_helper(
        "task-restore",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        "0" * 64,
    )
    assert wrong_digest.returncode != 0
    assert "stash digest conflict" in wrong_digest.stderr
    assert list((session / "metadata-change-set").iterdir()) == []

    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["stale"] = ["metadata"]
    state_path.write_text(json.dumps(state) + "\n")
    stale = run_helper(
        "task-restore",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        first_digest,
    )
    assert stale.returncode != 0
    assert "Snapshot is stale" in stale.stderr

    state = json.loads(state_path.read_text())
    del state["stale"]
    state_path.write_text(json.dumps(state) + "\n")
    (session / "metadata-change-set" / "unexpected.json").write_text("[]\n")
    nonempty = run_helper(
        "task-restore",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        first_digest,
    )
    assert nonempty.returncode != 0
    assert "Local Change Set must be empty" in nonempty.stderr
    (session / "metadata-change-set" / "unexpected.json").unlink()

    restored = run_helper(
        "task-restore",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        first_digest,
    )
    assert restored.returncode == 0, restored.stderr
    assert json.loads(restored.stdout) == {
        "task": "01",
        "area": "metadata",
        "digest": first_digest,
        "files": 1,
    }
    records = json.loads(
        (session / "metadata-change-set" / "source_object.json").read_text()
    )
    assert [record["system_code"] for record in records] == ["CRM"]
    status = json.loads(run_helper("status", "--session", str(session)).stdout)
    assert status["current"] == ["01", "metadata", "Stage Customer", "doing"]
    assert status["stashes"] == [["02", "metadata", 1, second_digest]]

    reviewed = run_helper("review", "--session", str(session), "--area", "metadata")
    assert reviewed.returncode == 0, reviewed.stderr
    review_state = run_helper(
        "task-state", "--session", str(session), "--task", "01", "--state", "review"
    )
    assert review_state.returncode == 0, review_state.stderr
    validated = run_helper("validate", "--session", str(session), "--area", "metadata")
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["valid"] is True
    accepted = run_helper(
        "accept",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--digest",
        first_digest,
    )
    assert accepted.returncode == 0, accepted.stderr


def test_task_state_cannot_orphan_pending_set_or_start_over_one(tmp_path: Path) -> None:
    session, _ = prepare_accepted_metadata_task(tmp_path)
    for target in ("waiting", "cancelled"):
        blocked = run_helper(
            "task-state",
            "--session",
            str(session),
            "--task",
            "01",
            "--state",
            target,
        )
        assert blocked.returncode != 0
        assert "task-stash" in blocked.stderr

    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["current"] = None
    state["tasks"][0][3] = "waiting"
    state_path.write_text(json.dumps(state) + "\n")
    starting = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Unsafe union",
        "--plan",
        '["Do not mix"]',
    )
    assert starting.returncode != 0
    assert "task-stash" in starting.stderr
    assert len(json.loads(state_path.read_text())["tasks"]) == 1
