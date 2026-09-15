"""Compare every Atlas modeling-quality scenario with the native evaluator."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPOSITORY_ROOT / "atlas/atlas-plugin/scripts/atlas-local.js"


def test_native_quality_evaluator_matches_all_javascript_scenarios(
    tmp_path: Path,
) -> None:
    powershell = (
        os.environ.get("ATLAS_POWERSHELL") or shutil.which("powershell.exe") or shutil.which("pwsh")
    )
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    captured = tmp_path / "cases.json"
    module = HELPER.parent.parent / "workbench" / "model-quality.js"
    suite = REPOSITORY_ROOT / "tests" / "atlas" / "workbench-quality.test.mjs"
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
        [
            powershell,
            "-NoProfile",
            "-File",
            str(runner),
            str(library),
            str(captured),
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    actual = json.loads(output.read_text())
    assert len(actual) == len(cases)
    for index, (case, value) in enumerate(zip(cases, actual, strict=True)):
        assert value == case["expected"], f"Quality parity case {index}"
