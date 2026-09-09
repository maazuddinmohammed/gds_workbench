"""Both local helpers plan identical bounded SQL from installed snapshot evidence."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.plugin_v2.test_gds_local_helper import HELPER, run_helper
from tests.plugin_v2.test_model_physical_history_parity import (
    OBJECT_FIELDS,
    write_graph_snapshot,
)


@pytest.mark.parametrize("runtime", ["javascript", "powershell"])
def test_profile_plan_uses_snapshot_scope_and_writes_bounded_artifacts(tmp_path, runtime):
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if runtime == "powershell" and not powershell:
        pytest.skip("PowerShell is not installed")
    initialized = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    obj = dict(
        tenant_code="TENANT_A",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="dbo",
        object_name="Customer",
        source_tenant_code="TENANT_A",
        zone_code="source",
        fc_object_schema="remote",
        fc_object_name="Customers",
        batch_attribute_name="Batch",
        is_active=True,
    )
    attrs = [
        {
            **obj,
            "attribute_name": "Batch" if i == 0 else f"Column{i}",
            "fc_attribute_name": f"Physical {i}",
            "attribute_data_type": "STRING",
            "attribute_ordinal_position": i + 1,
        }
        for i in range(71)
    ]
    rows = {
        "source_object": [obj],
        "source_attribute": attrs,
        "tenant": [{"tenant_code": "TENANT_A", "tenant_catalog": "demo", "is_active": True}],
        "connection": [
            {
                "tenant_code": "TENANT_A",
                "system_code": "CRM",
                "connection_code": "SOURCE",
                "foreign_catalog": "foreign",
                "is_active": True,
            }
        ],
    }
    keys = {
        "source_object": OBJECT_FIELDS,
        "source_attribute": [*OBJECT_FIELDS, "attribute_name"],
        "tenant": ["tenant_code"],
        "connection": ["tenant_code", "system_code", "connection_code"],
    }
    write_graph_snapshot(session, "metadata", rows, keys)
    write_graph_snapshot(
        session, "model", {"model_input_scope": [obj]}, {"model_input_scope": OBJECT_FIELDS}
    )
    task = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Profile",
        "--plan",
        '["Profile selected inputs"]',
    )
    assert task.returncode == 0, task.stderr
    plan = session / "batch-plan.json"
    plan.write_text(
        json.dumps(
            {
                "default_batch_id": None,
                "systems": [
                    {"source_tenant_code": "TENANT_A", "system_code": "CRM", "batch_id": "712'\\"}
                ],
            }
        )
    )
    args = ["profile-plan", "--session", str(session), "--plan-file", str(plan)]
    expected = run_helper(*args)
    assert expected.returncode == 0, expected.stderr
    if runtime == "javascript":
        actual = expected
    else:
        actual = subprocess.run(
            [powershell, "-NoProfile", "-File", str(HELPER.with_suffix(".ps1")), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    assert actual.returncode == 0, actual.stderr
    summary = json.loads(actual.stdout)
    reference = json.loads(Path(json.loads(expected.stdout)["manifest"]).read_text())
    manifest = json.loads(Path(summary["manifest"]).read_text())
    assert manifest == reference
    assert summary["query_count"] == 2 and summary["attribute_count"] == 71
    for query in manifest["queries"]:
        sql = (Path(summary["directory"]) / query["file"]).read_text()
        reference_sql = (Path(json.loads(expected.stdout)["directory"]) / query["file"]).read_text()
        assert sql == reference_sql
        assert "`foreign`.`remote`.`Customers`" in sql
        assert "WHERE `Physical 0`" in sql
        assert len(query["attributes"]) <= 50
    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["stale"] = ["metadata"]
    state_path.write_text(json.dumps(state))
    stale = run_helper(*args)
    assert stale.returncode != 0 and "stale" in stale.stderr
