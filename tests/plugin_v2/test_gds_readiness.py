from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER = (
    REPOSITORY_ROOT
    / "plugins"
    / "v2"
    / "gds"
    / "skills"
    / "gds"
    / "scripts"
    / "gds-local.js"
)


def run_helper(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(HELPER), *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def initialized_session(tmp_path: Path) -> Path:
    result = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert result.returncode == 0, result.stderr
    return Path(json.loads(result.stdout)["path"])


def write_snapshot(
    session: Path,
    area: str,
    *,
    dataset_name: str,
    records: list[dict[str, object]],
    revision: int = 8,
) -> None:
    root = session / area / f"{area}-snapshot"
    rows_path = f"data/{dataset_name}/rows.jsonl"
    schema_path = f"schemas/{area}/{dataset_name}.schema.json"
    rows = b"".join(
        (json.dumps(record, separators=(",", ":")) + "\n").encode()
        for record in records
    )
    schema = (
        json.dumps(
            {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
                "x-gds-change-set-eligible": True,
                "x-gds-canonical-key": ["id"],
            },
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    catalog: dict[str, object] = {
        "snapshot_kind": area,
        "sections": [
            {
                "name": "test",
                "datasets": [
                    {
                        "name": dataset_name,
                        "record_type": dataset_name,
                        "row_count": len(records),
                        "canonical_key": ["id"],
                        "rows_file": rows_path,
                        "schema_file": schema_path,
                    }
                ],
            }
        ],
    }
    if area == "model":
        catalog["model"] = {
            "model_id": 41,
            "model_name": "Customer Model",
            "model_revision": revision,
        }
    catalog_bytes = (json.dumps(catalog, separators=(",", ":")) + "\n").encode()
    members = {
        rows_path: rows,
        schema_path: schema,
        "catalog.json": catalog_bytes,
    }
    for relative, content in members.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest: dict[str, object] = {
        "snapshot_kind": area,
        "snapshot_id": f"{area}-snapshot-01",
        "catalog": {
            "path": "catalog.json",
            "sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        },
        "members": [
            {
                "path": relative,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
            for relative, content in members.items()
        ],
    }
    if area == "model":
        manifest.update(
            model_id=41,
            model_name="Customer Model",
            model_revision=revision,
        )
    else:
        manifest["tenant_code"] = "TENANT_A"
    (root / "manifest.json").write_text(json.dumps(manifest) + "\n")


def write_both_snapshots(session: Path) -> None:
    write_snapshot(
        session,
        "metadata",
        dataset_name="object",
        records=[{"id": 1}, {"id": 2}],
    )
    write_snapshot(
        session,
        "model",
        dataset_name="logical_entity",
        records=[{"id": 11}],
    )


@pytest.mark.parametrize(
    ("target", "areas"),
    (
        ("metadata-authoring", ["metadata"]),
        ("model-input-scope", ["metadata", "model"]),
        ("logical-build", ["metadata", "model"]),
        ("silver-registration", ["metadata", "model"]),
        ("logical-binding", ["metadata", "model"]),
        ("logical-mapping", ["metadata", "model"]),
        ("logical-code", ["metadata", "model"]),
        ("dimensional-build", ["metadata", "model"]),
        ("gold-registration", ["metadata", "model"]),
        ("dimensional-binding", ["metadata", "model"]),
        ("dimensional-mapping", ["metadata", "model"]),
        ("dimensional-code", ["metadata", "model"]),
        ("process-registration", ["metadata", "model"]),
    ),
)
def test_readiness_uses_only_target_snapshot_requirements(
    tmp_path: Path, target: str, areas: list[str]
) -> None:
    session = initialized_session(tmp_path)
    write_both_snapshots(session)

    result = run_helper("readiness", "--session", str(session), "--target", target)

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is True
    assert [item[0] for item in output["inputs"]] == areas
    assert set(output["counts"]) == set(areas)
    assert "records" not in output


def test_readiness_reports_missing_snapshot_without_loading_rows(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_snapshot(
        session,
        "metadata",
        dataset_name="object",
        records=[{"id": 1}],
    )

    result = run_helper(
        "readiness", "--session", str(session), "--target", "logical-build"
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is False
    assert ["snapshot_missing", 1] in output["blockers"]
    assert ["snapshot_missing", ["model"]] in output["examples"]
    assert output["resolution_prompt"].startswith("Create, download, and install each fresh")
    assert output["counts"] == {}


def test_readiness_reports_stale_snapshot(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_both_snapshots(session)
    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["stale"] = ["model"]
    state_path.write_text(json.dumps(state) + "\n")

    result = run_helper(
        "readiness", "--session", str(session), "--target", "logical-code"
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["ready"] is False
    assert output["blockers"] == [["snapshot_stale", 1]]
    assert output["examples"] == [["snapshot_stale", ["model"]]]


def test_validation_readiness_requires_bounded_unique_system_codes(
    tmp_path: Path,
) -> None:
    session = initialized_session(tmp_path)
    write_both_snapshots(session)

    missing = run_helper(
        "readiness", "--session", str(session), "--target", "validation"
    )
    duplicate = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "validation",
        "--system-codes",
        '["ERP","erp"]',
    )
    ready = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "validation",
        "--system-codes",
        '["ERP","CRM"]',
    )

    assert missing.returncode != 0
    assert "required for Validation readiness" in missing.stderr
    assert duplicate.returncode != 0
    assert "unique case-insensitively" in duplicate.stderr
    assert ready.returncode == 0, ready.stderr
    output = json.loads(ready.stdout)
    assert output["ready"] is True
    assert output["counts"]["selected_systems"] == 2


def test_system_codes_are_rejected_for_non_validation_targets(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)
    write_both_snapshots(session)

    result = run_helper(
        "readiness",
        "--session",
        str(session),
        "--target",
        "logical-build",
        "--system-codes",
        '["ERP"]',
    )

    assert result.returncode != 0
    assert "available only for Validation readiness" in result.stderr


def test_unknown_target_lists_current_names(tmp_path: Path) -> None:
    session = initialized_session(tmp_path)

    result = run_helper(
        "readiness", "--session", str(session), "--target", "qa"
    )

    assert result.returncode != 0
    assert "validation" in result.stderr
    assert "metadata-authoring" in result.stderr
    assert "qa" not in result.stderr.split("one of:", 1)[-1].split(".", 1)[0].split(", ")


@pytest.mark.parametrize(
    "command",
    ("contract-check", "mapping-proof", "generator-proof", "approve-reviewed"),
)
def test_removed_helper_commands_are_not_public(command: str) -> None:
    result = run_helper(command)

    assert result.returncode != 0
    assert f"Unknown command: {command}" in result.stderr


def test_command_contract_contains_no_removed_lifecycle_or_proof_commands() -> None:
    result = run_helper("command-contract")

    assert result.returncode == 0, result.stderr
    commands = json.loads(result.stdout)["commands"]
    assert "readiness" in commands
    assert "accept" in commands
    for removed in (
        "contract-check",
        "mapping-proof",
        "generator-proof",
        "approve-reviewed",
    ):
        assert removed not in commands
