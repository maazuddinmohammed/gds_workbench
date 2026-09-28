"""Compare every Atlas modeling-quality scenario with the native evaluator."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gds_etl_workbench.domain.modeling_records import has_mapping_transformation_content

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPOSITORY_ROOT / "atlas/atlas-plugin/scripts/atlas-local.js"


def test_native_mapping_empty_content_matches_shared_python(tmp_path: Path) -> None:
    powershell = (
        os.environ.get("ATLAS_POWERSHELL")
        or shutil.which("powershell.exe")
        or shutil.which("pwsh")
    )
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    cases: list[object] = [
        None,
        {},
        {"steps": [], "source_objects": []},
        {"nested": [None, {}, [], " \t\n\u001c\u0085"]},
        {"custom": False},
        {"custom": 0},
        {"custom": "\ufeff"},
        {"nested": [{"rule": "Use the source key."}]},
    ]
    case_file = tmp_path / "cases.json"
    case_file.write_text(json.dumps(cases))
    source = HELPER.with_suffix(".ps1").read_text()
    prefix = source[
        : source.rindex("\ntry {\n    $options = Parse-Options $RemainingArguments")
    ]
    library = tmp_path / "helper-library.ps1"
    helper_root = str(HELPER.parent).replace("'", "''")
    library.write_text(prefix.replace("$PSScriptRoot", f"'{helper_root}'"))
    runner = tmp_path / "run.ps1"
    runner.write_text("""
param([string]$Library, [string]$CasesPath, [string]$Output)
. $Library -Command 'test-library'
$results = New-Object Collections.ArrayList
foreach ($value in (ConvertFrom-GdsJson ([IO.File]::ReadAllText($CasesPath)))) {
    [void]$results.Add((Test-MappingTransformationContent $value))
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
            str(case_file),
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text()) == [
        has_mapping_transformation_content(value) for value in cases
    ]


def test_native_model_policy_matches_all_javascript_scenarios(tmp_path: Path) -> None:
    powershell = (
        os.environ.get("ATLAS_POWERSHELL")
        or shutil.which("powershell.exe")
        or shutil.which("pwsh")
    )
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    captured = tmp_path / "cases.json"
    module = HELPER.parent.parent / "workbench" / "validation" / "model-policy.js"
    suite = REPOSITORY_ROOT / "tests" / "atlas" / "workbench-policy.test.mjs"
    capture = tmp_path / "capture.cjs"
    capture.write_text("""
const fs = require('node:fs');
const {pathToFileURL} = require('node:url');
const api = require(process.argv[2]), evaluate = api.validate, cases = [];
api.validate = (model, metadata, options = {}) => {
  const expected = evaluate(model, metadata, options);
  cases.push(JSON.parse(JSON.stringify({
    model:[...model], metadata:metadata instanceof Map ? [...metadata] : [], options,
    expected:expected.map(item=>({code:item.code,dataset:item.dataset,
      fields:[item.field],severity:item.severity || 'error'}))})));
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
    assert len(cases) >= 10
    # Load the production functions without running its public CLI dispatcher.
    source = HELPER.with_suffix(".ps1").read_text()
    prefix = source[
        : source.rindex("\ntry {\n    $options = Parse-Options $RemainingArguments")
    ]
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
    $model = Get-Property $case.options 'model'
    [void]$results.Add(@(Get-AtlasModelPolicy $states $metadata $model))

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
        normalized = [
            {key: issue[key] for key in ("code", "dataset", "fields", "severity")}
            for issue in value
        ]
        assert sorted(
            normalized, key=lambda issue: json.dumps(issue, sort_keys=True)
        ) == sorted(
            case["expected"], key=lambda issue: json.dumps(issue, sort_keys=True)
        ), f"Policy parity case {index}"


def test_native_entity_record_rules_match_javascript(tmp_path: Path) -> None:
    powershell = (
        os.environ.get("ATLAS_POWERSHELL")
        or shutil.which("powershell.exe")
        or shutil.which("pwsh")
    )
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    module = HELPER.parent.parent / "workbench" / "validation" / "common.js"
    suite = REPOSITORY_ROOT / "tests" / "atlas" / "entity-record-validation.test.mjs"
    captured = tmp_path / "schema-cases.json"
    capture = tmp_path / "capture.cjs"
    capture.write_text("""
const fs = require('node:fs');
const {pathToFileURL} = require('node:url');
const api = require(process.argv[2]), evaluate = api.validateSchema, cases = [];
api.validateSchema = (value, schema) => {
  const expected = evaluate(value, schema);
  cases.push(JSON.parse(JSON.stringify({value, schema, expected})));
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
    assert len(cases) == 11
    source = HELPER.with_suffix(".ps1").read_text()
    prefix = source[
        : source.rindex("\ntry {\n    $options = Parse-Options $RemainingArguments")
    ]
    library = tmp_path / "helper-library.ps1"
    helper_root = str(HELPER.parent).replace("'", "''")
    library.write_text(prefix.replace("$PSScriptRoot", f"'{helper_root}'"))
    runner = tmp_path / "run.ps1"
    runner.write_text("""
param([string]$Library, [string]$CasesPath, [string]$Output)
. $Library -Command 'test-library'
$cases = ConvertFrom-GdsJson ([IO.File]::ReadAllText($CasesPath))
$results = New-Object Collections.ArrayList
foreach ($case in $cases) {
    [void]$results.Add(@(Get-SchemaIssues -Value $case.value -Schema $case.schema))
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
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    actual = json.loads(output.read_text())
    assert actual == [case["expected"] for case in cases]
