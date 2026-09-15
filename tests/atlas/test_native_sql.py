"""Replay generated SQL policy through the native Windows-compatible validator."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "atlas/atlas-plugin/scripts/atlas-local.ps1"


def test_native_generated_sql_matches_javascript_and_record_selection(tmp_path: Path) -> None:
    powershell = (
        os.environ.get("ATLAS_POWERSHELL") or shutil.which("powershell.exe") or shutil.which("pwsh")
    )
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    captured = tmp_path / "cases.json"
    capture = tmp_path / "capture.cjs"
    capture.write_text(r"""
const fs = require('node:fs');
const {pathToFileURL} = require('node:url');
const api = require(process.argv[2]), validate = api.validateGeneratedSql, cases = [];
api.validateGeneratedSql = text => {
  const expected = validate(text);
  cases.push({kind:'sql',text,expected});
  return expected;
};
for (const text of [null, {}, '', ' ', '; ;', 'SELECT ID, FROM bronze.X',
  'SELECT 1 AS ID', 'SELECT \'a; -- x\'\'y\' AS Label FROM bronze.X',
  'SELECT "Delete", `Set` FROM "bronze"."X"',
  'SELECT ID FROM bronze.X /* unclosed', 'SELECT ID FROM bronze.X -- comment',
  'SELECT ID FROM bronze.X /* done */', 'SELECT ID FROM',
  'SELECT ID FROM bronze.X WHERE ID IN (SELECT ID FROM bronze.Y)',
  'SELECT ID FROM read_files(\'file\')', 'SELECT ID FROM range(10)',
  'CREATE OR REPLACE TEMPORARY VIEW "v.a" AS SELECT ID FROM bronze.X; SELECT ID FROM "v.a"',
  'CREATE OR REPLACE TEMP VIEW V AS SELECT ID FROM bronze.X; SELECT ID FROM v',
  'CREATE OR REPLACE TEMP VIEW v AS SELECT ID FROM bronze.X; ' +
    'SELECT ID FROM bronze.X UNION SELECT ID FROM v',
  'CREATE OR REPLACE TEMP VIEW v AS SELECT ID FROM v; SELECT ID FROM v',
  'CREATE OR REPLACE TEMP VIEW v AS VALUES (1); SELECT ID FROM v',
  'SELECT a.ID FROM bronze.A a JOIN bronze.B b ON a.ID=b.ID',
  'SELECT a.ID FROM bronze.A a, bronze.B b, Missing c',
  'WITH a AS (SELECT ID FROM bronze.A) SELECT ID FROM a',
  'SELECT ID FROM bronze.X; SELECT ID FROM bronze.Y']) api.validateGeneratedSql(text);
for (const [declared, referenced] of [
  ['İ', 'i\u0307'], ['İ', 'i'], ['ΟΣ', 'ος'], ['ΟΣ', 'οσ'], ['ΟΣΑ', 'οσα'],
  ['Σ', 'σ'], ['Σ', 'ς'], ['Α\u0301Σ', 'α\u0301ς'], ['ΑΣ\u0301Α', 'ασ\u0301α'],
  ['ΑΣ\u0301', 'ας\u0301'], ['ΑΣ\u2019', 'ας\u2019'], ['ΑΣ\u2019Α', 'ασ\u2019α'],
  ['\u{10400}', '\u{10428}'], ['Ａ', 'ａ'], ['AΣ\u0345', 'aς\u0345'],
]) api.validateGeneratedSql(`CREATE OR REPLACE TEMP VIEW "${declared}" AS ` +
  `SELECT ID FROM bronze.X; SELECT ID FROM "${referenced}"`);
api.validateGeneratedSql('CREATE OR REPLACE TEMP VIEW "ΟΣ" AS SELECT ID FROM bronze.X; ' +
  'CREATE OR REPLACE TEMP VIEW "ος" AS SELECT ID FROM bronze.X; SELECT ID FROM "ος"');
const definition = {name:'generated_code',canonical_key:['generated_code_name']};
const record = (name, extra={}) => ({generated_code_name:name, artifact_type:'sql_file',
  generated_code_status:'active',generated_code_content:'SELECT * FROM bronze.X',...extra});
const preserved = record('Preserved'), edited = record('Edited');
const baseline = [preserved, edited, record('Insensitive')];
const pending = [record('New'), {...preserved}, {...edited,description:'changed'},
  record('Inactive',{generated_code_status:'inactive'}),
  record('Python',{artifact_type:'python_file'}),
  record('IsActiveFalse',{is_active:false}), record('StatusOverrides',{status:'inactive'}),
  record('Valid',{generated_code_content:'SELECT ID FROM bronze.X'}),
  record('NoStatus',{generated_code_status:null}), record('insensitive'),
  record('NullSql',{generated_code_content:null})];
for (const records of [[], [["generated_code", {definition,baseline,pending}]]]) {
  const expected = api.validateCodeRecords(new Map(records)).map(issue => ({
    severity:'error',dataset:issue.dataset,record:issue.record,code:issue.code,
    fields:[issue.field],message:issue.message}));
  cases.push({kind:'records',records,expected});
}
process.on('exit', () => fs.writeFileSync(process.argv[4], JSON.stringify(cases)));
import(pathToFileURL(process.argv[3]).href);
""")
    result = subprocess.run(
        [
            "node",
            str(capture),
            str(HELPER.parent.parent / "workbench/validation/sql.js"),
            str(ROOT / "tests/atlas/workbench-sql.test.mjs"),
            str(captured),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    cases = json.loads(captured.read_text())
    assert len(cases) >= 50
    source = HELPER.read_text()
    prefix = source[: source.rindex("\ntry {\n    $options = Parse-Options $RemainingArguments")]
    library = tmp_path / "helper-library.ps1"
    helper_root = str(HELPER.parent).replace("'", "''")
    library.write_text(prefix.replace("$PSScriptRoot", f"'{helper_root}'"))
    runner = tmp_path / "run.ps1"
    runner.write_text("""
param([string]$Library, [string]$CasesPath, [string]$Output, [string]$Culture)
$cultureInfo = [Globalization.CultureInfo]::GetCultureInfo($Culture)
[Threading.Thread]::CurrentThread.CurrentCulture = $cultureInfo
. $Library -Command 'test-library'
$cases = ConvertFrom-GdsJson ([IO.File]::ReadAllText($CasesPath))
$results = New-Object Collections.ArrayList
foreach ($case in $cases) {
    if ($case.kind -ceq 'sql') {
        [void]$results.Add(@(Get-AtlasGeneratedSqlIssues $case.text))
    }
    else {
        $states = @(foreach ($pair in $case.records) {
            $raw = $pair[1]
            [pscustomobject]@{Dataset=$raw.definition; Baseline=$raw.baseline; Pending=$raw.pending}
        })
        [void]$results.Add(@(Get-AtlasGeneratedCodeIssues $states))
    }
}
[IO.File]::WriteAllText($Output, (ConvertTo-GdsJson @($results)), $script:Utf8NoBom)
""")
    for culture in ("en-US", "tr-TR"):
        output = tmp_path / f"results-{culture}.json"
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-File",
                str(runner),
                str(library),
                str(captured),
                str(output),
                culture,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        actual = json.loads(output.read_text())
        assert len(actual) == len(cases)
        for index, (case, value) in enumerate(zip(cases, actual, strict=True)):
            assert value == case["expected"], f"SQL parity case {index}, {culture}: {case}"


def test_native_cli_runs_sql_policy_without_revalidating_retained_code(tmp_path: Path) -> None:
    from tests.atlas import test_workspace as workspace

    powershell = (
        os.environ.get("ATLAS_POWERSHELL") or shutil.which("powershell.exe") or shutil.which("pwsh")
    )
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    root = workspace.workspace(tmp_path)
    snapshot = root / "model/model-snapshot"
    catalog_path = snapshot / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    definition = {
        "name": "generated_code",
        "row_count": 1,
        "canonical_key": ["generated_code_name"],
        "rows_file": "data/generated_code.jsonl",
        "schema_file": "schemas/generated_code.schema.json",
    }
    catalog["sections"][0]["datasets"].append(definition)
    catalog_path.write_text(json.dumps(catalog))
    original = {
        "generated_code_name": "Preserved",
        "artifact_type": "sql_file",
        "generated_code_status": "active",
        "generated_code_content": "SELECT * FROM bronze.X",
    }
    (snapshot / str(definition["rows_file"])).write_text(json.dumps(original) + "\n")
    (snapshot / str(definition["schema_file"])).write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {field: {"type": "string"} for field in original},
                "required": list(original),
                "x-gds-change-set-eligible": True,
            }
        )
    )
    workspace.fixtures.write_snapshot_manifest(
        snapshot, kind="model", snapshot_id="model-snapshot-01", model_revision=8
    )
    pending = root / "model-change-set"
    pending.mkdir()
    retained = [
        original,
        {**original, "generated_code_name": "Python", "artifact_type": "python_file"},
        {**original, "generated_code_name": "Inactive", "generated_code_status": "inactive"},
    ]
    helpers = [
        ["node", str(HELPER.with_suffix(".js"))],
        [powershell, "-NoProfile", "-File", str(HELPER)],
    ]
    for records, expected in [
        (retained, []),
        (retained + [{**original, "generated_code_name": "New"}], ["code.projection"]),
    ]:
        (pending / "generated_code.json").write_text(json.dumps(records))
        for helper in helpers:
            result = subprocess.run(
                helper + ["validate", "--session", str(root), "--area", "model"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, result.stderr
            report = json.loads(result.stdout)
            assert report["valid"] is (not expected)
            assert [issue["code"] for issue in report["issues"]] == expected
