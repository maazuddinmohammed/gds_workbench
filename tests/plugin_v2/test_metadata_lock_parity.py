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
    ("scenario", "expected"),
    [
        ("parent_attribute", "object_locked"),
        ("parent_unlock", "object_locked"),
        ("attribute_edit", "attribute_locked"),
        ("attribute_unlock", "attribute_locked"),
        ("attribute_unchanged", "attribute_locked"),
        ("normalized_attribute", "attribute_locked"),
        ("unlocked_attribute", None),
        ("other_attribute", None),
        ("missing_inferred_type", "schema"),
        ("missing_attribute_lock", "schema"),
    ],
)
def test_metadata_lock_validation_matches_across_helpers(
    tmp_path: Path, runtime: str, scenario: str, expected: str | None
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if runtime == "powershell" and powershell is None:
        pytest.skip("Windows PowerShell 5.1 or PowerShell is not installed")
    initialized = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    snapshot = session / "metadata/metadata-snapshot"
    catalog_path = snapshot / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    objects_path = snapshot / "data/source_object.jsonl"
    objects = [json.loads(line) for line in objects_path.read_text().splitlines()]
    for row in objects:
        row["is_locked"] = scenario.startswith("parent")
    objects_path.write_text("".join(json.dumps(row) + "\n" for row in objects))
    attribute = {
        **objects[0],
        "attribute_name": "CustomerID",
        "attribute_description": None,
        "attribute_inferred_data_type": None,
        "is_locked": scenario != "unlocked_attribute",
    }
    (snapshot / "data/source_attribute.jsonl").write_text(json.dumps(attribute) + "\n")
    for descriptor in catalog["sections"][0]["datasets"]:
        is_attribute = descriptor["name"] == "source_attribute"
        descriptor["record_type"] = "attribute" if is_attribute else "object"
        descriptor["row_count"] = 1 if is_attribute else len(objects)
        schema_path = snapshot / descriptor["schema_file"]
        schema = json.loads(schema_path.read_text())
        schema["x-gds-record-type"] = descriptor["record_type"]
        schema["properties"]["is_locked"] = {"type": "boolean"}
        schema["required"].append("is_locked")
        if is_attribute:
            for field in ("attribute_description", "attribute_inferred_data_type"):
                schema["properties"][field] = {"type": ["string", "null"]}
                schema["required"].append(field)
            schema["x-gds-references"][0]["target_record_type"] = "object"
        schema_path.write_text(json.dumps(schema))
    catalog_path.write_text(json.dumps(catalog))
    write_snapshot_manifest(snapshot, kind="metadata", snapshot_id="metadata-lock-fixture")
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Check metadata locks",
        "--plan",
        '["Validate"]',
    )
    assert added.returncode == 0, added.stderr
    pending = dict(attribute)
    dataset = "source_attribute"
    if scenario == "parent_unlock":
        dataset = "source_object"
        pending = {**objects[0], "is_locked": False}
    elif scenario == "attribute_unlock":
        pending["is_locked"] = False
    elif scenario == "normalized_attribute":
        pending["attribute_name"] = " customerid "
        pending["object_name"] = " customer "
    elif scenario == "other_attribute":
        pending["attribute_name"] = "DisplayName"
        pending["is_locked"] = False
    elif scenario.startswith("missing_"):
        pending["is_locked"] = False
        missing = (
            "attribute_inferred_data_type" if scenario == "missing_inferred_type" else "is_locked"
        )
        del pending[missing]
    elif scenario != "attribute_unchanged":
        pending["attribute_description"] = "Changed description."
    if scenario.startswith("missing_"):
        attribute["is_locked"] = False
        (snapshot / "data/source_attribute.jsonl").write_text(json.dumps(attribute) + "\n")
        write_snapshot_manifest(snapshot, kind="metadata", snapshot_id="metadata-lock-fixture")
    (session / "metadata-change-set" / f"{dataset}.json").write_text(json.dumps([pending]))
    arguments = ["validate", "--session", str(session), "--area", "metadata"]
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
        command,
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["valid"] is (expected is None)
    assert {repair["code"] for repair in output["repairs"]} == ({expected} if expected else set())
