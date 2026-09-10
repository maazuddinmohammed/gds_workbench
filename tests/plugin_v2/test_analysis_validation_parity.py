"""A claimed Analysis verdict must agree with its aggregate evidence everywhere."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph
from gds_etl_workbench.domain.modeling_records import ANALYSIS_VALIDATION_FIELDS
from gds_etl_workbench.domain.snapshots.model import DATASETS_BY_NAME, build_model_dataset_schema

from tests.mcp.model_test_fixtures import (
    complete_model_graph,
    complete_physical_scope,
    empty_model_snapshot,
)
from tests.plugin_v2.test_gds_local_helper import run_helper, write_snapshot_manifest
from tests.plugin_v2.test_model_physical_history_parity import OBJECT_FIELDS, write_graph_snapshot

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins/v2/gds/skills/gds/scripts"


@pytest.mark.parametrize("runtime", ["server", "javascript", "powershell"])
@pytest.mark.parametrize(
    ("changes", "valid"),
    [
        ({}, True),
        (dict.fromkeys(ANALYSIS_VALIDATION_FIELDS), True),
        ({"validation_source_missing_target_count": 1, "validation_unused_target_count": 1}, False),
        ({"validation_source_missing_target_count": 1, "validation_unused_target_count": 1,
          "validation_result": "unsupported"}, True),
        ({"validation_target_non_null_count": 6,
          "validation_duplicate_target_key_count": 1}, False),
        ({"validation_target_non_null_count": 6, "validation_duplicate_target_key_count": 1,
          "validation_result": "unsupported"}, True),
        ({"validation_result": "unsupported"}, False),
        ({"validation_result": "inconclusive"}, False),
        ({"validation_source_non_null_count": 0, "validation_source_distinct_count": 0,
          "validation_unused_target_count": 5, "validation_result": "inconclusive"}, True),
        ({"validation_source_non_null_count": 0, "validation_source_distinct_count": 0,
          "validation_unused_target_count": 5}, False),
        ({"validation_target_non_null_count": 0, "validation_target_distinct_count": 0,
          "validation_source_missing_target_count": 5, "validation_result": "inconclusive"}, True),
        ({"validation_target_non_null_count": 0, "validation_target_distinct_count": 0,
          "validation_source_missing_target_count": 5}, False),
        ({"validation_source_distinct_count": 10}, False),
        ({"validation_source_distinct_count": 0}, False),
        ({"validation_target_distinct_count": 6}, False),
        ({"validation_target_distinct_count": 0}, False),
        ({"validation_source_missing_target_count": 6, "validation_result": "unsupported"}, False),
        ({"validation_unused_target_count": 6}, False),
        ({"validation_duplicate_target_key_count": 1, "validation_result": "unsupported"}, False),
        ({"validation_source_non_null_count": None}, False),
        ({"validation_source_distinct_count": 4}, False),
        ({"validation_source_distinct_count": 4, "validation_unused_target_count": 1}, True),
    ],
    ids=[
        "supported", "unmeasured", "false_support_orphans", "unsupported_orphans",
        "false_support_duplicates", "unsupported_duplicates", "false_unsupported",
        "false_inconclusive", "empty_source", "false_support_empty_source", "empty_target",
        "false_support_empty_target", "source_distinct_overflow", "source_zero_distinct",
        "target_distinct_overflow", "target_zero_distinct", "orphans_overflow", "unused_overflow",
        "duplicate_mismatch", "partial_evidence", "matched_distinct_mismatch",
        "asymmetric_distinct_counts",
    ],
)
def test_analysis_evidence_integrity_matches_across_paths(
    tmp_path: Path, runtime: str, changes: dict[str, object], valid: bool,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if runtime == "powershell" and powershell is None:
        pytest.skip("Windows PowerShell 5.1 or PowerShell is not installed")
    graph = complete_model_graph()
    record = graph["analysis_result"][0]
    record.update(changes)
    if runtime == "server":
        result = validate_future_graph(
            snapshot=empty_model_snapshot(), staged_documents=graph,
            physical_scope=complete_physical_scope(),
        )
        assert result.valid is valid
        if not valid:
            assert {issue.code for issue in result.issues} == {"record_schema_invalid"}
        return

    initialized = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    objects = [
        {field: record[f"{side}_{field}"] for field in OBJECT_FIELDS}
        for side in ("from", "to")
    ]
    attributes = [
        {**obj, "attribute_name": record[f"{side}_attribute_name"], "is_active": True}
        for obj, side in zip(objects, ("from", "to"), strict=True)
    ]
    write_graph_snapshot(
        session, "metadata",
        {"object": [{**obj, "source_tenant_code": "TENANT_A", "zone_code": "source",
                     "is_active": True} for obj in objects], "attribute": attributes},
        {"object": OBJECT_FIELDS, "attribute": [*OBJECT_FIELDS, "attribute_name"]},
    )
    write_graph_snapshot(
        session, "model",
        {"model_details": graph["model_details"],
         "model_input_scope": [{**obj, "is_active": True, "model_input_scope_is_locked": False}
                               for obj in objects], "analysis_result": []},
        {"model_details": [], "model_input_scope": OBJECT_FIELDS,
         "analysis_result": list(DATASETS_BY_NAME["analysis_result"].canonical_key)},
    )
    snapshot = session / "model/model-snapshot"
    (snapshot / "schemas/analysis_result.json").write_text(
        json.dumps(build_model_dataset_schema(DATASETS_BY_NAME["analysis_result"]))
    )
    write_snapshot_manifest(
        snapshot, kind="model", snapshot_id="analysis-evidence", model_revision=8,
    )
    added = run_helper(
        "task-add", "--session", str(session), "--area", "model",
        "--title", "Check evidence", "--plan", '["Validate"]',
    )
    assert added.returncode == 0, added.stderr
    (session / "model-change-set/analysis_result.json").write_text(json.dumps([record]))
    command = (
        ["node", str(SCRIPTS / "gds-local.js")]
        if runtime == "javascript"
        else [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive",
              "-File", str(SCRIPTS / "gds-local.ps1")]
    )
    completed = subprocess.run(
        [*command, "validate", "--session", str(session), "--area", "model"],
        text=True, capture_output=True, timeout=30, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    assert output["valid"] is valid
    if not valid:
        assert {issue["code"] for issue in output["repairs"]} == {"schema"}
