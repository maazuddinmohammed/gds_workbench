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
@pytest.mark.parametrize("masking", ["none", "partial", "all", "batch", "propagated"])
def test_profile_plan_uses_snapshot_scope_and_writes_bounded_artifacts(
    tmp_path: Path, runtime: str, masking: str,
) -> None:
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
            "is_masking_required": masking == "all" or (masking == "partial" and i == 1)
            or (masking == "batch" and i == 0),
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
    scoped_object = obj
    if masking == "propagated":
        scoped_object = {**obj, "object_schema": "bronze", "zone_code": "bronze"}
        rows["bronze_object"] = [scoped_object]
        rows["bronze_attribute"] = [{**attr, "object_schema": "bronze"} for attr in attrs]
        # An inactive Source Attribute cannot erase masking on its still-mapped Bronze copy.
        attrs[1].update(is_masking_required=True, is_active=False)
        mapping = {
            f"{side}_{field}": endpoint[field]
            for side, endpoint in (("source", obj), ("target", scoped_object))
            for field in OBJECT_FIELDS
        }
        rows["ingestion_object_mapping"] = [{**mapping, "is_active": True}]
        rows["ingestion_attribute_mapping"] = [{
            **mapping, "source_attribute_name": "Column1", "target_attribute_name": "Column1",
            "is_active": True,
        }]
        keys.update(
            bronze_object=OBJECT_FIELDS,
            bronze_attribute=[*OBJECT_FIELDS, "attribute_name"],
            ingestion_object_mapping=list(mapping),
            ingestion_attribute_mapping=[
                *mapping, "source_attribute_name", "target_attribute_name",
            ],
        )
    write_graph_snapshot(session, "metadata", rows, keys)
    write_graph_snapshot(
        session, "model", {"model_input_scope": [scoped_object]},
        {"model_input_scope": OBJECT_FIELDS},
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
    if runtime == "javascript":
        actual = expected
    else:
        actual = subprocess.run(
            [str(powershell), "-NoProfile", "-File", str(HELPER.with_suffix(".ps1")), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    if masking == "batch":
        assert expected.returncode != 0 and actual.returncode != 0
        assert "Masked batch Attribute" in actual.stderr
        assert not list((session / "working").rglob("profiling-*"))
        return
    assert expected.returncode == 0, expected.stderr
    assert actual.returncode == 0, actual.stderr
    summary = json.loads(actual.stdout)
    reference = json.loads(Path(json.loads(expected.stdout)["manifest"]).read_text())
    manifest = json.loads(Path(summary["manifest"]).read_text())
    assert manifest == reference
    excluded_count = {"none": 0, "partial": 1, "all": 71, "propagated": 1}[masking]
    assert summary["query_count"] == (0 if masking == "all" else 2)
    assert summary["attribute_count"] == 71 - excluded_count
    assert summary["excluded_attribute_count"] == excluded_count
    assert len(manifest["coverage"]) == 1
    coverage = manifest["coverage"][0]
    assert coverage["active_attribute_count"] == 71
    assert coverage["planned_attribute_count"] == 71 - excluded_count
    assert len(coverage["excluded"]) == excluded_count
    assert all(entry["reason"] == "masking_required" for entry in coverage["excluded"])
    assert len(list(Path(summary["directory"]).glob("*.sql"))) == summary["query_count"]
    for query in manifest["queries"]:
        sql = (Path(summary["directory"]) / query["file"]).read_text()
        reference_sql = (Path(json.loads(expected.stdout)["directory"]) / query["file"]).read_text()
        assert sql == reference_sql
        if masking == "propagated":
            assert "`demo`.`bronze`.`Customer`" in sql
            assert "WHERE `Batch`" in sql
            assert "`Column1`" not in sql
        else:
            assert "`foreign`.`remote`.`Customers`" in sql
            assert "WHERE `Physical 0`" in sql
        if masking == "partial":
            assert "`Physical 1`" not in sql
        assert len(query["attributes"]) <= 50
    state_path = session / "session.json"
    state = json.loads(state_path.read_text())
    state["stale"] = ["metadata"]
    state_path.write_text(json.dumps(state))
    stale = run_helper(*args) if runtime == "javascript" else subprocess.run(
        [str(powershell), "-NoProfile", "-File", str(HELPER.with_suffix(".ps1")), *args],
        capture_output=True, text=True, timeout=30,
    )
    assert stale.returncode != 0 and "stale" in stale.stderr
