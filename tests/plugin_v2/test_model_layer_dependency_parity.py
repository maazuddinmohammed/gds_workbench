"""Exercise effective Model graph lifecycle rules through both local helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.plugin_v2.test_gds_local_helper import (
    run_helper,
    write_metadata_snapshot,
    write_snapshot_manifest,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPOSITORY_ROOT / "plugins/v2/gds/skills/gds/scripts"


@pytest.mark.parametrize("runtime", ["javascript", "powershell"])
@pytest.mark.parametrize(
    ("layer", "scenario"),
    [
        (layer, scenario)
        for layer in ("conceptual", "logical", "dimensional")
        for scenario in (
            "normalized",
            "from_parent_inactive",
            "to_parent_inactive",
            "from_attribute_inactive",
            "to_attribute_inactive",
            "inactive_history",
            "inactive_missing_reference",
        )
        if layer != "conceptual" or "attribute_inactive" not in scenario
    ],
)
def test_model_layer_dependencies_match_across_helpers(
    tmp_path: Path,
    runtime: str,
    layer: str,
    scenario: str,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if runtime == "powershell" and powershell is None:
        pytest.skip("Windows PowerShell 5.1 or PowerShell is not installed")
    initialized = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    parent_type = f"{layer}_{'object' if layer == 'conceptual' else 'entity'}"
    attribute_type = f"{layer}_attribute"
    relationship_type = f"{layer}_relationship"
    parent_name = f"{parent_type}_name"
    parents = [
        {parent_name: "Straße", f"{parent_type}_status": "active"},
        {parent_name: "Order", f"{parent_type}_status": "active"},
    ]
    attributes = [
        {
            parent_name: "STRASSE",
            f"{attribute_type}_name": "ID",
            f"{attribute_type}_status": "active",
        },
        {
            parent_name: " order ",
            f"{attribute_type}_name": "ID",
            f"{attribute_type}_status": "active",
        },
    ]
    relationship = {
        f"{relationship_type}_name": "Connects",
        f"{relationship_type}_status": "active",
        f"from_{parent_name}": " strasse ",
        f"to_{parent_name}": "ORDER",
    }
    if layer != "conceptual":
        relationship.update(
            {f"from_{attribute_type}_name": " id ", f"to_{attribute_type}_name": "Id"}
        )
    if "parent_inactive" in scenario:
        parents[int(scenario.startswith("to_"))][f"{parent_type}_status"] = "inactive"
    if "attribute_inactive" in scenario:
        attributes[int(scenario.startswith("to_"))][f"{attribute_type}_status"] = "inactive"
    if scenario.startswith("inactive_"):
        for parent in parents:
            parent[f"{parent_type}_status"] = "inactive"
        for attribute in attributes:
            attribute[f"{attribute_type}_status"] = "inactive"
        relationship[f"{relationship_type}_status"] = "inactive"
    if scenario == "inactive_missing_reference":
        parents = parents[1:]
    pending_parent = None
    if "parent_inactive" in scenario:
        index = int(scenario.startswith("to_"))
        pending_parent = dict(parents[index])
        parents[index][f"{parent_type}_status"] = "active"

    rows: dict[str, list[dict[str, str]]] = {
        "model_details": [{}],
        "model_input_scope": [],
        parent_type: parents,
        relationship_type: [relationship],
    }
    keys = {
        "model_details": [],
        "model_input_scope": ["object_name"],
        parent_type: [parent_name],
        relationship_type: [f"{relationship_type}_name"],
    }
    references = {
        relationship_type: [
            {
                "columns": [f"{prefix}_{parent_name}"],
                "target_record_type": parent_type,
                "target_columns": [parent_name],
            }
            for prefix in ("from", "to")
        ]
    }
    if layer != "conceptual":
        rows[attribute_type] = attributes
        keys[attribute_type] = [parent_name, f"{attribute_type}_name"]
        references[attribute_type] = [
            {
                "columns": [parent_name],
                "target_record_type": parent_type,
                "target_columns": [parent_name],
            }
        ]
        references[relationship_type] = [
            {
                "columns": [f"{prefix}_{parent_name}", f"{prefix}_{attribute_type}_name"],
                "target_record_type": attribute_type,
                "target_columns": [parent_name, f"{attribute_type}_name"],
            }
            for prefix in ("from", "to")
        ]
    snapshot = session / "model/model-snapshot"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    datasets: list[dict[str, object]] = []
    for name, records in rows.items():
        descriptor: dict[str, object] = {
            "name": name,
            "record_type": name,
            "canonical_key": keys[name],
            "row_count": len(records),
            "rows_file": f"data/{name}.jsonl",
            "schema_file": f"schemas/{name}.json",
        }
        datasets.append(descriptor)
        (snapshot / f"data/{name}.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records)
        )
        (snapshot / f"schemas/{name}.json").write_text(
            json.dumps(
                {
                    "type": "object",
                    "x-gds-record-type": name,
                    "x-gds-change-set-eligible": True,
                    "x-gds-references": references.get(name, []),
                }
            )
        )
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "model",
                "sections": [{"name": layer, "datasets": datasets}],
            }
        )
    )
    write_snapshot_manifest(
        snapshot, kind="model", snapshot_id="dependency-fixture", model_revision=8
    )
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Review dependencies",
        "--plan",
        '["Validate"]',
    )
    assert added.returncode == 0, added.stderr
    if pending_parent is not None:
        (session / "model-change-set" / f"{parent_type}.json").write_text(
            json.dumps([pending_parent])
        )
    arguments = ["validate", "--session", str(session), "--area", "model"]
    command = (
        ["node", str(SCRIPTS / "gds-local.js"), *arguments]
        if runtime == "javascript"
        else [
            str(powershell),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(SCRIPTS / "gds-local.ps1"),
            *arguments,
        ]
    )
    result = subprocess.run(
        command, cwd=REPOSITORY_ROOT, text=True, capture_output=True, timeout=30, check=False
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    expected_valid = scenario in {"normalized", "inactive_history"}
    assert output["valid"] is expected_valid
    issues = output["repairs"]
    if scenario == "inactive_missing_reference":
        assert any(issue["code"] in {"broken_reference", "reference_not_found"} for issue in issues)
        assert all(issue["code"] != "active_dependency_invalid" for issue in issues)
    elif not expected_valid:
        assert {issue["code"] for issue in issues} == {"active_dependency_invalid"}
        expected = {
            (
                relationship_type,
                f"{layer}_{'object' if layer == 'conceptual' else 'attribute'}_name",
            )
        }
        if layer != "conceptual" and "parent_inactive" in scenario:
            expected.add((attribute_type, parent_name))
        assert {(issue["dataset"], issue["fields"][0]) for issue in issues} == expected
