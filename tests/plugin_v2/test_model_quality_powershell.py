"""Run every pure quality evaluator scenario through native PowerShell too."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.plugin_v2.test_gds_local_helper import (
    HELPER,
    REPOSITORY_ROOT,
    run_helper,
    write_metadata_snapshot,
    write_model_snapshot,
)


def test_native_quality_evaluator_matches_all_javascript_scenarios(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    captured = tmp_path / "cases.json"
    module = HELPER.parent.parent / "workbench" / "model-quality.js"
    suite = REPOSITORY_ROOT / "tests" / "plugin_v2" / "model_quality.test.mjs"
    capture = tmp_path / "capture.cjs"
    capture.write_text("""
const fs = require('node:fs');
const {pathToFileURL} = require('node:url');
const api = require(process.argv[2]), evaluate = api.evaluateQuality, cases = [];
api.evaluateQuality = (model, decisions, options = {}) => {
  const expected = evaluate(model, decisions, options);
  cases.push(JSON.parse(JSON.stringify({
    model: model instanceof Map ? [...model] : null, decisions, expected,
    notes: options.noteFiles instanceof Map ? Object.fromEntries(options.noteFiles)
      : options.noteFiles || {},
    metadata: options.metadataMap instanceof Map ? [...options.metadataMap] : [],
  })));
  return expected;
};
process.on('exit', () => fs.writeFileSync(process.argv[4], JSON.stringify(cases)));
import(pathToFileURL(process.argv[3]).href);
""")
    result = subprocess.run(
        ["node", str(capture), str(module), str(suite), str(captured)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    cases = json.loads(captured.read_text())
    assert len(cases) >= 30
    # Load the production functions without running its public CLI dispatcher.
    source = HELPER.with_suffix(".ps1").read_text()
    prefix = source[: source.rindex("\ntry {\n    $options = Parse-Options $RemainingArguments")]
    library = tmp_path / "helper-library.ps1"
    helper_root = str(HELPER.parent).replace("'", "''")
    library.write_text(prefix.replace("$PSScriptRoot", f"'{helper_root}'"))
    runner = tmp_path / "run.ps1"
    runner.write_text("""
param([string]$Library, [string]$CasesPath, [string]$Output)
. $Library -Command 'test-library'
function Convert-States($Pairs) {
    foreach ($pair in $Pairs) {
        $raw = $pair[1]
        $state = [ordered]@{ Dataset = (Get-Property $raw 'definition') }
        foreach ($field in @('baseline', 'pending', 'effective')) {
            if (Test-Property $raw $field) {
                $name = $field.Substring(0,1).ToUpperInvariant() + $field.Substring(1)
                $state[$name] = Get-Property $raw $field
            }
        }
        [pscustomobject]$state
    }
}
$results = New-Object Collections.ArrayList
$cases = ConvertFrom-GdsJson ([IO.File]::ReadAllText($CasesPath))
foreach ($case in $cases) {
    $states = if ($null -eq $case.model) { $null } else { @(Convert-States $case.model) }
    $metadata = @(Convert-States $case.metadata)
    $notes = @{}
    foreach ($name in @(Get-PropertyNames $case.notes)) {
        $notes[$name] = Get-Property $case.notes $name
    }
    [void]$results.Add((Get-ModelingQuality $states $case.decisions $notes $metadata))
}
[IO.File]::WriteAllText($Output, (ConvertTo-GdsJson @($results)), $script:Utf8NoBom)
""")
    output = tmp_path / "results.json"
    result = subprocess.run(
        [powershell, "-NoProfile", "-File", str(runner), str(library), str(captured), str(output)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    actual = json.loads(output.read_text())
    assert len(actual) == len(cases)
    for index, (case, value) in enumerate(zip(cases, actual, strict=True)):
        assert value == case["expected"], f"Quality parity case {index}"


def test_native_quality_report_bytes_acceptance_and_changed_evidence(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    initialized = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_snapshot(session)
    write_model_snapshot(session)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Review identity",
        "--plan",
        '["Review identity"]',
    )
    assert added.returncode == 0, added.stderr
    entity = {"logical_entity_name": "Straße", "logical_entity_status": "active", "sources": []}
    attribute = {
        "logical_entity_name": "Straße",
        "logical_attribute_name": "ID",
        "logical_attribute_status": "active",
        "logical_attribute_is_nullable": False,
        "logical_attribute_is_primary_key": True,
        "logical_attribute_is_natural_key": True,
        "logical_attribute_is_surrogate_key": False,
        "logical_attribute_is_audit_column": False,
        "logical_attribute_data_type": "BIGINT",
        "sources": [],
    }
    for dataset, row in (("logical_entity", entity), ("logical_attribute", attribute)):
        (session / "model-change-set" / f"{dataset}.json").write_text(json.dumps([row]))
    first = run_helper("validate", "--session", str(session), "--area", "model")
    assert first.returncode == 0, first.stderr
    first_output = json.loads(first.stdout)
    assert first_output["quality"]["status"] == "needs_evidence"
    decisions_path = Path(first_output["quality"]["decisions"])
    decisions = json.loads(decisions_path.read_text())
    note_path = session / "working" / "01" / "object-analysis" / "identity.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("Synthetic identity evidence: ID identifies one customer.\n")
    decisions["entities"][0].update(
        {
            "decision": "ID determines one customer and its lifecycle attributes.",
            "evidence": [{"note": "working/01/object-analysis/identity.md"}],
        }
    )
    decisions_path.write_text(json.dumps(decisions))
    reference = run_helper("validate", "--session", str(session), "--area", "model")
    assert reference.returncode == 0, reference.stderr
    expected = json.loads(reference.stdout)
    assert expected["quality"]["status"] == "evidence_present"
    report_path = Path(expected["quality"]["report"])
    report_bytes = report_path.read_bytes()
    native = [powershell, "-NoProfile", "-File", str(HELPER.with_suffix(".ps1"))]
    validated = subprocess.run(
        [*native, "validate", "--session", str(session), "--area", "model"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["quality"] == expected["quality"]
    assert report_path.read_bytes() == report_bytes
    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["tasks"][0][3] = "review"
    state_path.write_text(json.dumps(state))
    accepted = subprocess.run(
        [
            *native,
            "accept",
            "--session",
            str(session),
            "--area",
            "model",
            "--digest",
            expected["digest"],
            "--override",
            "true",
            "--reason",
            "Synthetic schema fixture",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert accepted.returncode == 0, accepted.stderr
    acceptance = json.loads((session / "tasks" / "01.accept.json").read_text())
    assert acceptance[-1]["modeling_quality"]["report_sha256"]
    note_path.write_text(note_path.read_text() + "Changed after acknowledgement.\n")
    cached = subprocess.run(
        [
            *native,
            "draft-cache",
            "--session",
            str(session),
            "--area",
            "model",
            "--id",
            "00000000-0000-4000-8000-000000000123",
            "--revision",
            "1",
            "--status",
            "active",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert cached.returncode != 0
    assert "changed after acknowledgement" in cached.stderr
    status = subprocess.run(
        [*native, "status", "--session", str(session)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["acceptance"] is None
    assert "changed after acknowledgement" in json.loads(status.stdout)["acceptance_issue"]
