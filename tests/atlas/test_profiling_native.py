"""Exercise production native planners against the JavaScript safety scenarios."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.atlas.test_workspace import fixtures, run, workspace

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "atlas/atlas-plugin/scripts"


def test_native_profiling_and_batch_type_parity(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    captured = tmp_path / "cases.json"
    capture = tmp_path / "capture.cjs"
    capture.write_text("""
const fs = require('node:fs'), {pathToFileURL} = require('node:url');
const api = require(process.argv[2]), cases = [];
const path = require('node:path');
const analysis = require(path.join(path.dirname(process.argv[2]), 'analysis.js'));
const calls = [[api, 'planProfiling'], [api, 'validateBatchType'], [analysis, 'planAnalysis']];
for (const [module, name] of calls) {
  const original = module[name];
  module[name] = (...args) => {
    const saved = JSON.parse(JSON.stringify(args));
    try {
      const expected = original(...args);
      cases.push({name,args:saved,value:expected ?? null}); return expected;
    }
    catch (error) { cases.push({name,args:saved,error:true}); throw error; }
  };
}
process.on('exit', () => fs.writeFileSync(process.argv[4], JSON.stringify(cases)));
import(pathToFileURL(process.argv[3]).href);
""")
    result = subprocess.run(
        [
            "node",
            str(capture),
            str(SCRIPTS / "profiling.js"),
            str(ROOT / "tests/atlas/profiling.test.mjs"),
            str(captured),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    cases = json.loads(captured.read_text())
    assert len(cases) >= 35
    source = (SCRIPTS / "atlas-local.ps1").read_text()
    prefix = source[: source.rindex("\ntry {\n    $options = Parse-Options $RemainingArguments")]
    library = tmp_path / "library.ps1"
    library.write_text(prefix.replace("$PSScriptRoot", "'" + str(SCRIPTS).replace("'", "''") + "'"))
    runner = tmp_path / "run.ps1"
    runner.write_text("""
param([string]$Library, [string]$Planner, [string]$CasesPath, [string]$Output)
. $Library -Command 'test-library'
. $Planner
$results = New-Object Collections.ArrayList
foreach ($case in (ConvertFrom-GdsJson ([IO.File]::ReadAllText($CasesPath)))) {
    try {
        $value = $null
        if ($case.name -ceq 'validateBatchType') {
            Assert-ProfileBatchType $case.args[0] $case.args[1]
        }
        elseif ($case.name -ceq 'planAnalysis') {
            $value = @(Plan-Analysis $case.args[0] $case.args[1] $case.args[2])
        }
        else { $value = Plan-Profiling $case.args[0] $case.args[1] $case.args[2] }
        [void]$results.Add(@{value=$value})
    } catch { [void]$results.Add(@{error=$true;message=$_.Exception.Message}) }
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
            str(SCRIPTS / "analysis.ps1"),
            str(captured),
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    actual = json.loads(output.read_text())
    assert len(actual) == len(cases)
    for index, (case, value) in enumerate(zip(cases, actual, strict=True)):
        assert value.get("error", False) == case.get("error", False), (index, value)
        if not case.get("error"):
            assert value["value"] == case["value"], f"Native planning parity case {index}"


def test_native_aggregate_manifest_matches_node_in_never_policy(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not installed")
    root = workspace(tmp_path)
    run("sql-policy", "--session", str(root), "--policy", "never")
    obj = {
        "tenant_code": "TENANT_A",
        "system_code": "CRM",
        "connection_code": "SRC",
        "object_schema": "dbo",
        "object_name": "Customer",
        "source_tenant_code": "TENANT_A",
        "zone_code": "source",
        "fc_object_schema": "remote",
        "fc_object_name": "Customer",
        "batch_attribute_name": "Batch",
        "is_active": True,
    }
    rows = {
        "source_object": [obj],
        "source_attribute": [
            {
                **obj,
                "attribute_name": name,
                "fc_attribute_name": name,
                "attribute_ordinal_position": i + 1,
                "attribute_data_type": "STRING",
            }
            for i, name in enumerate(["Batch", "CustomerID"])
        ],
        "tenant": [{"tenant_code": "TENANT_A", "tenant_catalog": "owner", "is_active": True}],
        "connection": [
            {
                "tenant_code": "TENANT_A",
                "system_code": "CRM",
                "connection_code": "SRC",
                "foreign_catalog": "foreign",
                "is_active": True,
            }
        ],
    }
    keys = [
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
    ]
    snapshot = root / "metadata/metadata-snapshot"
    catalog = json.loads((snapshot / "catalog.json").read_text())
    datasets: list[dict[str, Any]] = []
    for name, records in rows.items():
        key = (
            keys + ["attribute_name"]
            if name == "source_attribute"
            else keys
            if name == "source_object"
            else keys[:3]
            if name == "connection"
            else keys[:1]
        )
        datasets.append(
            {
                "name": name,
                "record_type": name,
                "row_count": len(records),
                "canonical_key": key,
                "rows_file": f"data/{name}.jsonl",
                "schema_file": f"schemas/{name}.schema.json",
            }
        )
        (snapshot / f"data/{name}.jsonl").write_text("\n".join(map(json.dumps, records)) + "\n")
        (snapshot / f"schemas/{name}.schema.json").write_text(json.dumps({"type": "object"}))
    catalog["sections"][0]["datasets"] = datasets
    (snapshot / "catalog.json").write_text(json.dumps(catalog))
    fixtures.write_snapshot_manifest(snapshot, kind="metadata", snapshot_id="metadata-1")
    model = root / "model/model-snapshot"
    (model / "data/model_input_scope.jsonl").write_text(json.dumps(obj) + "\n")
    (model / "schemas/model_input_scope.schema.json").write_text(json.dumps({"type": "object"}))
    model_catalog = json.loads((model / "catalog.json").read_text())
    model_catalog["sections"][0]["datasets"].append(
        {
            "name": "model_input_scope",
            "record_type": "model_input_scope",
            "row_count": 1,
            "canonical_key": keys,
            "rows_file": "data/model_input_scope.jsonl",
            "schema_file": "schemas/model_input_scope.schema.json",
        }
    )
    (model / "catalog.json").write_text(json.dumps(model_catalog))
    fixtures.write_snapshot_manifest(model, kind="model", snapshot_id="model-1", model_revision=8)
    selections = {
        "systems": [
            {
                "source_tenant_code": "TENANT_A",
                "system_code": "CRM",
                "batch_ids": ["10", "11"],
            }
        ]
    }
    plan = tmp_path / "selection.json"
    plan.write_text(
        json.dumps(
            {
                "selections": selections,
                "execution_connections": [
                    {
                        "connection_id": 13,
                        "source_tenant_codes": ["TENANT_A"],
                        "is_global_data_store": False,
                    }
                ],
            }
        )
    )
    expected = run("profile-plan", "--session", str(root), "--plan-file", str(plan))
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-File",
            str(SCRIPTS / "atlas-local.ps1"),
            "profile-plan",
            "--session",
            str(root),
            "--plan-file",
            str(plan),
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    actual = json.loads(result.stdout)
    assert actual["query_count"] == expected["query_count"] == 1
    assert json.loads(Path(actual["manifest"]).read_text()) == json.loads(
        Path(expected["manifest"]).read_text()
    )
    assert Path(actual["directory"]).is_relative_to(root / ".atlas/temp")
    assert (Path(actual["directory"]) / "0001.sql").read_bytes() == (
        Path(expected["directory"]) / "0001.sql"
    ).read_bytes()
