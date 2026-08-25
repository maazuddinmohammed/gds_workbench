from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from uuid import UUID

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER = (
    REPOSITORY_ROOT
    / "plugins"
    / "v1"
    / "gds"
    / "skills"
    / "manage-gds-model"
    / "scripts"
    / "model-change-set.js"
)
CHANGE_SET_ID = UUID("4a4d40a7-7fc9-48ab-b1dc-c14e23ee64ad")
MODEL_DATASETS = (
    "model_details",
    "model_scope",
    "profiling_profile",
    "analysis_result",
    "modeling_assertion_document",
    "modeling_assertion_record",
    "conceptual_object",
    "conceptual_relationship",
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "mapping_dependency",
    "mapping_object",
    "mapping_attribute",
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(HELPER), *(str(value) for value in arguments)],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _workspace(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    gds = tmp_path / "GDS"
    gds.mkdir()
    snapshot_path = gds / "model-snapshot"
    schemas = snapshot_path / "schemas"
    rows = snapshot_path / "datasets" / "conceptual_object"
    schemas.mkdir(parents=True)
    rows.mkdir(parents=True)
    manifest = {
        "schema_version": "2.0",
        "snapshot_kind": "model",
        "snapshot_id": "a82504f8-254c-4ff5-93b6-04a4bdc8a29d",
        "model_id": 41,
        "model_name": "Sales Model",
        "model_revision": 7,
    }
    catalog_datasets = [
        {
            "name": dataset,
            "schema_file": f"schemas/{dataset}.schema.json",
            "rows_file": f"datasets/{dataset}/rows.jsonl",
        }
        for dataset in MODEL_DATASETS
    ]
    catalog_file = snapshot_path / "catalog.json"
    catalog_file.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "snapshot_kind": "model",
                "database_ids_included": False,
                "model": {
                    "model_id": 41,
                    "model_name": "Sales Model",
                    "model_revision": 7,
                },
                "sections": [{"name": "model", "datasets": catalog_datasets}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    conceptual_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "$defs": {},
        "properties": {
            "conceptual_object_name": {"type": "string", "minLength": 1},
            "conceptual_object_definition": {
                "anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}]
            },
        },
        "required": [
            "conceptual_object_name",
            "conceptual_object_definition",
        ],
        "x-gds-dataset": "conceptual_object",
        "x-gds-section": "conceptual",
        "x-gds-database-ids-included": False,
        "x-gds-change-set-eligible": True,
        "x-gds-canonical-key": ["conceptual_object_name"],
    }
    schema_file = schemas / "conceptual_object.schema.json"
    schema_file.write_text(
        json.dumps(conceptual_schema, indent=2) + "\n",
        encoding="utf-8",
    )
    baseline = {
        "conceptual_object_name": "Customer",
        "conceptual_object_definition": "A buyer.",
    }
    rows_file = rows / "rows.jsonl"
    rows_file.write_text(
        json.dumps(baseline) + "\n",
        encoding="utf-8",
    )
    members = []
    for file in (catalog_file, schema_file, rows_file):
        content = file.read_bytes()
        members.append(
            {
                "path": file.relative_to(snapshot_path).as_posix(),
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    manifest["catalog"] = {
        "path": "catalog.json",
        "sha256": members[0]["sha256"],
    }
    manifest["members"] = members
    (snapshot_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    change_set = gds / "model-change-set"
    datasets = change_set / "datasets"
    datasets.mkdir(parents=True)
    conceptual = dict(baseline)
    conceptual["conceptual_object_definition"] = "SENSITIVE-LOCAL-DEFINITION"
    (datasets / "conceptual_object.json").write_text(
        json.dumps([conceptual], indent=2) + "\n",
        encoding="utf-8",
    )
    (change_set / "model-change-set.json").write_text(
        json.dumps(
            {
                "format_version": "1.0",
                "model": {
                    "model_id": manifest["model_id"],
                    "model_name": manifest["model_name"],
                    "model_revision": manifest["model_revision"],
                },
                "snapshot": {
                    "snapshot_id": manifest["snapshot_id"],
                    "path": "../model-snapshot",
                    "usage": "local",
                    "outdated_snapshot_warning_acknowledged": False,
                },
                "server_change_set": {
                    "model_change_set_id": None,
                    "draft_revision": None,
                    "status": "local",
                },
                "datasets": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return change_set, conceptual


def _bind(
    change_set: Path, *, current_model_revision: int = 7
) -> subprocess.CompletedProcess[str]:
    return _run(
        "bind",
        "--change-set",
        change_set,
        "--model-id",
        41,
        "--current-model-revision",
        current_model_revision,
        "--model-change-set-id",
        CHANGE_SET_ID,
        "--draft-revision",
        1,
        "--server-status",
        "active",
        "--created",
        "true",
    )


def test_new_model_draft_handoff_binds_reviews_and_records_server_state(
    tmp_path: Path,
) -> None:
    change_set, _ = _workspace(tmp_path)

    bound = _bind(change_set)
    assert bound.returncode == 0, bound.stderr
    state = _json(change_set / "model-change-set.json")
    assert state["server_change_set"] == {
        "model_change_set_id": str(CHANGE_SET_ID),
        "draft_revision": 1,
        "status": "active",
    }
    assert state["snapshot"]["usage"] == "fresh"

    checked = _run("validate", "--change-set", change_set)
    assert checked.returncode == 0, checked.stderr
    assert "dataset=conceptual_object|1|" in checked.stdout
    assert "SENSITIVE-LOCAL-DEFINITION" not in checked.stdout + checked.stderr

    reviewed = _run("prepare-stage", "--change-set", change_set)
    assert reviewed.returncode == 0, reviewed.stderr
    assert "stage_ready=true" in reviewed.stdout
    review = _json(change_set / "stage-review.json")
    assert review["datasets"]["conceptual_object"]["actions"]["update"] == 1
    assert "SENSITIVE-LOCAL-DEFINITION" not in json.dumps(review)

    staged = _run(
        "record-stage",
        "--change-set",
        change_set,
        "--model-change-set-id",
        CHANGE_SET_ID,
        "--expected-current-revision",
        1,
        "--server-revision",
        2,
        "--server-dataset-count",
        "conceptual_object=1",
    )
    assert staged.returncode == 0, staged.stderr
    state = _json(change_set / "model-change-set.json")
    assert state["server_change_set"]["draft_revision"] == 2
    assert state["datasets"]["conceptual_object"]["staged_revision"] == 2

    validated = _run(
        "record-validation",
        "--change-set",
        change_set,
        "--model-change-set-id",
        CHANGE_SET_ID,
        "--expected-current-revision",
        2,
        "--server-revision",
        2,
        "--server-status",
        "validated",
    )
    assert validated.returncode == 0, validated.stderr
    assert (
        _json(change_set / "model-change-set.json")["server_change_set"]["status"]
        == "validated"
    )


def test_model_handoff_rejects_stale_baseline_without_changing_local_state(
    tmp_path: Path,
) -> None:
    change_set, _ = _workspace(tmp_path)
    before = (change_set / "model-change-set.json").read_bytes()

    result = _bind(change_set, current_model_revision=8)

    assert result.returncode == 2
    assert "rebase before binding" in result.stderr
    assert (change_set / "model-change-set.json").read_bytes() == before


def test_resumed_model_draft_requires_every_server_record_to_be_reconciled(
    tmp_path: Path,
) -> None:
    change_set, local_record = _workspace(tmp_path)
    server_record = dict(local_record)
    server_record["conceptual_object_definition"] = "Existing server work"
    server_draft = tmp_path / "server-draft.json"
    server_draft.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "model_id": 41,
                "model_change_set_id": str(CHANGE_SET_ID),
                "status": "active",
                "draft_revision": 1,
                "dataset_counts": [{"dataset": "conceptual_object", "record_count": 1}],
                "datasets": {"conceptual_object": [server_record]},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    conflict = _run(
        "bind",
        "--change-set",
        change_set,
        "--model-id",
        41,
        "--current-model-revision",
        7,
        "--model-change-set-id",
        CHANGE_SET_ID,
        "--draft-revision",
        1,
        "--server-status",
        "active",
        "--created",
        "false",
        "--server-draft",
        server_draft,
    )
    assert conflict.returncode == 2
    assert "has not preserved a resumed server record" in conflict.stderr
    assert (
        _json(change_set / "model-change-set.json")["server_change_set"]["status"]
        == "local"
    )

    (change_set / "datasets" / "conceptual_object.json").write_text(
        json.dumps([server_record], indent=2) + "\n",
        encoding="utf-8",
    )
    reconciled = _run(
        "bind",
        "--change-set",
        change_set,
        "--model-id",
        41,
        "--current-model-revision",
        7,
        "--model-change-set-id",
        CHANGE_SET_ID,
        "--draft-revision",
        1,
        "--server-status",
        "active",
        "--created",
        "false",
        "--server-draft",
        server_draft,
    )
    assert reconciled.returncode == 0, reconciled.stderr
    assert "resumed_server_draft_verified=true" in reconciled.stdout


def test_model_stage_state_rejects_a_stale_review(tmp_path: Path) -> None:
    change_set, local_record = _workspace(tmp_path)
    assert _bind(change_set).returncode == 0
    assert _run("prepare-stage", "--change-set", change_set).returncode == 0
    local_record["conceptual_object_definition"] = "Changed after review"
    (change_set / "datasets" / "conceptual_object.json").write_text(
        json.dumps([local_record], indent=2) + "\n",
        encoding="utf-8",
    )

    result = _run(
        "record-stage",
        "--change-set",
        change_set,
        "--model-change-set-id",
        CHANGE_SET_ID,
        "--expected-current-revision",
        1,
        "--server-revision",
        2,
        "--server-dataset-count",
        "conceptual_object=1",
    )

    assert result.returncode == 2
    assert "review is stale" in result.stderr
    assert (
        _json(change_set / "model-change-set.json")["server_change_set"][
            "draft_revision"
        ]
        == 1
    )


def test_model_stage_review_rejects_a_tampered_snapshot_baseline(
    tmp_path: Path,
) -> None:
    change_set, _ = _workspace(tmp_path)
    assert _bind(change_set).returncode == 0
    baseline = (
        change_set.parent
        / "model-snapshot"
        / "datasets"
        / "conceptual_object"
        / "rows.jsonl"
    )
    baseline.write_text(
        json.dumps(
            {
                "conceptual_object_name": "Customer",
                "conceptual_object_definition": "Tampered baseline",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run("prepare-stage", "--change-set", change_set)

    assert result.returncode == 2
    assert "does not match its Snapshot" in result.stderr
    assert not (change_set / "stage-review.json").exists()


def test_model_handoff_rejects_snapshot_member_parent_symlinks(
    tmp_path: Path,
) -> None:
    change_set, _ = _workspace(tmp_path)
    rows_directory = (
        change_set.parent / "model-snapshot" / "datasets" / "conceptual_object"
    )
    content = (rows_directory / "rows.jsonl").read_bytes()
    (rows_directory / "rows.jsonl").unlink()
    rows_directory.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "rows.jsonl").write_bytes(content)
    try:
        rows_directory.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlink unavailable: {error}")

    result = _bind(change_set)

    assert result.returncode == 2
    assert "cannot traverse a symbolic link" in result.stderr
    assert (
        _json(change_set / "model-change-set.json")["server_change_set"]["status"]
        == "local"
    )
