"""Registered Analysis probe selections produce reviewable aggregate SQL only."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.plugin_v2.test_gds_local_helper import HELPER, run_helper
from tests.plugin_v2.test_model_physical_history_parity import OBJECT_FIELDS, write_graph_snapshot

PLANNER = HELPER.with_name("analysis.js")


def analysis_fixture(catalog: str = "foreign", schema: str = "remote") -> dict[str, Any]:
    objects = [
        {"tenant_code": "TENANT_A", "system_code": "CRM", "connection_code": "SOURCE",
         "object_schema": "dbo", "object_name": name, "source_tenant_code": "TENANT_A",
         "zone_code": "source", "fc_object_schema": schema, "fc_object_name": physical,
         "is_active": True}
        for name, physical in (("Observation", "analysis_source"), ("Reference", "analysis_target"))
    ]
    attributes = [
        {**{field: obj[field] for field in OBJECT_FIELDS}, "attribute_name": name,
         "fc_attribute_name": name, "attribute_data_type": "STRING", "is_active": True,
         "is_masking_required": False}
        for obj in objects for name in ("customer_id", "region", "name", "line")
    ]
    keys = [{field: obj[field] for field in OBJECT_FIELDS} for obj in objects]
    return {
        "metadata": {"source_object": objects, "source_attribute": attributes,
                     "tenant": [{"tenant_code": "TENANT_A", "tenant_catalog": "store"}],
                     "connection": [{"tenant_code": "TENANT_A", "system_code": "CRM",
                                     "connection_code": "SOURCE", "foreign_catalog": catalog}]},
        "scope": objects,
        "plan": {"scope": "all_rows", "probes": [
            {"id": "identity", "kind": "key", "object": keys[0],
             "columns": ["customer_id", "region"]},
            {"id": "descriptor", "kind": "dependency", "object": keys[0],
             "determinants": ["customer_id", "region"], "dependents": ["name"]},
            {"id": "reference", "kind": "join",
             "from": {"object": keys[0], "columns": ["customer_id", "region"]},
             "to": {"object": keys[1], "columns": ["customer_id", "region"]}},
        ]},
    }


def plan_queries(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["node", "-e", "const fs=require('node:fs'),p=JSON.parse(fs.readFileSync(0,'utf8'));"
         "process.stdout.write(JSON.stringify(require(process.argv[1]).planAnalysis(p.metadata,p.scope,p.plan)))",
         str(PLANNER)],
        input=json.dumps(fixture), text=True, capture_output=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("runtime", ["javascript", "powershell"])
def test_analysis_plan_cli_uses_snapshot_scope_and_preserves_query_parity(
    tmp_path: Path, runtime: str,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if runtime == "powershell" and not powershell:
        pytest.skip("PowerShell is not installed")
    initialized = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    fixture = analysis_fixture()
    write_graph_snapshot(session, "metadata", fixture["metadata"], {
        "source_object": OBJECT_FIELDS, "source_attribute": [*OBJECT_FIELDS, "attribute_name"],
        "tenant": ["tenant_code"], "connection": OBJECT_FIELDS[:3],
    })
    write_graph_snapshot(session, "model", {"model_input_scope": fixture["scope"]},
                         {"model_input_scope": OBJECT_FIELDS})
    task = run_helper("task-add", "--session", str(session), "--area", "model", "--title",
                      "Analysis", "--plan", '["Measure signaled candidates"]')
    assert task.returncode == 0, task.stderr
    plan = session / "probes.json"
    plan.write_text(json.dumps(fixture["plan"]))
    arguments = ["analysis-plan", "--session", str(session), "--plan-file", str(plan)]
    expected = run_helper(*arguments)
    assert expected.returncode == 0, expected.stderr
    actual = expected if runtime == "javascript" else subprocess.run(
        [str(powershell), "-NoProfile", "-File", str(HELPER.with_suffix(".ps1")), *arguments],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert actual.returncode == 0, actual.stderr
    summary = json.loads(actual.stdout)
    reference_summary = json.loads(expected.stdout)
    manifest = json.loads(Path(summary["manifest"]).read_text())
    assert manifest == json.loads(Path(reference_summary["manifest"]).read_text())
    assert summary["query_count"] == 3
    assert manifest["model_revision"] == 8
    assert manifest["model_snapshot_id"] and manifest["metadata_snapshot_id"]
    for query in manifest["queries"]:
        sql = (Path(summary["directory"]) / query["file"]).read_text()
        assert sql == (Path(reference_summary["directory"]) / query["file"]).read_text()
        assert query["execution_state"] == "not_run" and query["max_result_rows"] == 1
    assert not list((session / "model-change-set").glob("*.json"))
    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["stale"] = ["metadata"]
    state_path.write_text(json.dumps(state))
    stale = run_helper(*arguments) if runtime == "javascript" else subprocess.run(
        [str(powershell), "-NoProfile", "-File", str(HELPER.with_suffix(".ps1")), *arguments],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert stale.returncode != 0 and "stale" in stale.stderr
