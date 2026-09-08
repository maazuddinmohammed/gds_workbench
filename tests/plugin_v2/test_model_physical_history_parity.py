"""Retained physical evidence survives metadata lifecycle changes in both helpers."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.plugin_v2.test_gds_local_helper import run_helper, write_snapshot_manifest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPOSITORY_ROOT / "plugins/v2/gds/skills/gds/scripts"
OBJECT_FIELDS = ["tenant_code", "system_code", "connection_code", "object_schema", "object_name"]


def write_graph_snapshot(
    session: Path,
    area: str,
    rows: dict[str, list[dict[str, Any]]],
    keys: dict[str, list[str]],
) -> None:
    snapshot = session / area / f"{area}-snapshot"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    datasets: list[dict[str, object]] = []
    for name, records in rows.items():
        datasets.append(
            {
                "name": name,
                "record_type": name,
                "canonical_key": keys[name],
                "row_count": len(records),
                "rows_file": f"data/{name}.jsonl",
                "schema_file": f"schemas/{name}.json",
            }
        )
        (snapshot / f"data/{name}.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records)
        )
        (snapshot / f"schemas/{name}.json").write_text(
            json.dumps(
                {
                    "type": "object",
                    "x-gds-record-type": name,
                    "x-gds-change-set-eligible": True,
                    "x-gds-references": [],
                }
            )
        )
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": area,
                "sections": [{"name": area, "datasets": datasets}],
            }
        )
    )
    write_snapshot_manifest(
        snapshot,
        kind=area,
        snapshot_id=f"history-{area}",
        model_revision=8 if area == "model" else None,
    )


@pytest.mark.parametrize("runtime", ["javascript", "powershell"])
@pytest.mark.parametrize(
    ("scenario", "valid"),
    [
        ("unchanged", True),
        ("attribute_inactive", True),
        ("scope_deactivation", True),
        ("nested_lock", True),
        ("nested_deactivation", True),
        ("new_inactive", False),
        ("reactivation", False),
        ("description_edit", False),
        ("source_edit", False),
        ("profile_edit", False),
        ("wrong_owner", False),
        ("missing_attribute", False),
    ],
)
def test_physical_history_does_not_authorize_new_evidence(
    tmp_path: Path,
    runtime: str,
    scenario: str,
    valid: bool,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if runtime == "powershell" and powershell is None:
        pytest.skip("Windows PowerShell 5.1 or PowerShell is not installed")
    initialized = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    physical = {
        "tenant_code": "GDS",
        "system_code": "CRM",
        "connection_code": "SHARED",
        "object_schema": "bronze",
        "object_name": "Customer",
    }
    physical_attribute = {**physical, "attribute_name": "ID"}
    obj: dict[str, Any] = {
        **physical,
        "source_tenant_code": "TENANT_A",
        "zone_code": "bronze",
        "is_active": False,
    }
    attr: dict[str, Any] = {**physical_attribute, "is_active": True}
    if scenario == "attribute_inactive":
        obj["is_active"] = True
        attr["is_active"] = False
    if scenario == "wrong_owner":
        obj["source_tenant_code"] = "OTHER"
    write_graph_snapshot(
        session,
        "metadata",
        {
            "object": [obj],
            "attribute": [] if scenario == "missing_attribute" else [attr],
            "system": [{"system_code": "CRM", "is_active": True}],
        },
        {
            "object": OBJECT_FIELDS,
            "attribute": [*OBJECT_FIELDS, "attribute_name"],
            "system": ["system_code"],
        },
    )
    source: dict[str, Any] = {
        "support_source_type": "object",
        "source_object": physical,
        "source_order": 1,
        "rationale": "Registered source.",
        "status": "active",
        "is_locked": False,
    }
    entity: dict[str, Any] = {
        "logical_entity_name": "Customer",
        "logical_entity_description": "Customer concept.",
        "logical_entity_status": "active",
        "logical_entity_is_locked": False,
        "sources": [source],
        "submodels": [],
    }
    scope: dict[str, Any] = {**physical, "is_active": True, "model_input_scope_is_locked": False}
    profile: dict[str, Any] = {
        **physical_attribute,
        "row_count": 5,
        "non_null_count": 5,
        "null_count": 0,
    }
    rows: dict[str, list[dict[str, Any]]] = {
        "model_details": [{"model_name": "History"}],
        "model_input_scope": [scope],
        "profiling_profile": [profile],
        "logical_entity": [entity],
    }
    keys = {
        "model_details": [],
        "model_input_scope": OBJECT_FIELDS,
        "profiling_profile": [*OBJECT_FIELDS, "attribute_name"],
        "logical_entity": ["logical_entity_name"],
    }
    staged: dict[str, list[dict[str, Any]]] = {}
    changed = copy.deepcopy(entity)
    if scenario == "scope_deactivation":
        staged["model_input_scope"] = [{**scope, "is_active": False}]
    elif scenario == "profile_edit":
        staged["profiling_profile"] = [{**profile, "row_count": 6, "non_null_count": 6}]
    elif scenario == "new_inactive":
        rows["logical_entity"] = []
        changed["logical_entity_status"] = "inactive"
        staged["logical_entity"] = [changed]
    elif scenario == "reactivation":
        entity["logical_entity_status"] = "inactive"
        staged["logical_entity"] = [changed]
    elif scenario in {"nested_lock", "nested_deactivation", "description_edit", "source_edit"}:
        if scenario == "nested_lock":
            changed["sources"][0]["is_locked"] = True
        elif scenario == "nested_deactivation":
            changed["sources"][0]["status"] = "inactive"
        elif scenario == "description_edit":
            changed["logical_entity_description"] = "A different authored description."
        else:
            changed["sources"][0]["rationale"] = "Newly authored source evidence."
        staged["logical_entity"] = [changed]
    write_graph_snapshot(session, "model", rows, keys)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Retain historical evidence",
        "--plan",
        '["Validate"]',
    )
    assert added.returncode == 0, added.stderr
    for name, records in staged.items():
        (session / "model-change-set" / f"{name}.json").write_text(json.dumps(records))
    arguments = ["validate", "--session", str(session), "--area", "model"]
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
        command, cwd=REPOSITORY_ROOT, text=True, capture_output=True, timeout=30, check=False
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["valid"] is valid
    if not valid:
        assert any(issue["code"] == "model_input_reference_invalid" for issue in output["repairs"])


@pytest.mark.parametrize("runtime", ["javascript", "powershell"])
@pytest.mark.parametrize("rebound", [False, True])
def test_retained_attribute_binding_requires_the_same_parent_target(
    tmp_path: Path,
    runtime: str,
    rebound: bool,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if runtime == "powershell" and powershell is None:
        pytest.skip("Windows PowerShell 5.1 or PowerShell is not installed")
    initialized = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT_A")
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    physical = {
        "tenant_code": "GDS",
        "system_code": "GDS",
        "connection_code": "SHARED",
        "object_schema": "silver",
        "object_name": "Customer",
    }
    objects = [
        {
            **physical,
            "object_name": name,
            "source_tenant_code": "TENANT_A",
            "zone_code": "silver",
            "is_active": True,
        }
        for name in ("Customer", "OtherCustomer")
    ]
    attributes = [{**item, "attribute_name": "ID", "is_active": False} for item in objects]
    write_graph_snapshot(
        session,
        "metadata",
        {
            "object": objects,
            "attribute": attributes,
            "system": [{"system_code": "GDS", "is_active": True}],
        },
        {
            "object": OBJECT_FIELDS,
            "attribute": [*OBJECT_FIELDS, "attribute_name"],
            "system": ["system_code"],
        },
    )
    entity = {"modeled_entity_type": "logical_entity", "modeled_entity_name": "Customer"}
    binding = {**entity, **physical, "model_object_binding_status": "active"}
    rows: dict[str, list[dict[str, Any]]] = {
        "model_details": [{"model_name": "History"}],
        "model_input_scope": [],
        "logical_entity": [{"logical_entity_name": "Customer", "logical_entity_status": "active"}],
        "logical_attribute": [
            {
                "logical_entity_name": "Customer",
                "logical_attribute_name": "ID",
                "logical_attribute_status": "active",
            }
        ],
        "model_object_binding": [binding],
        "model_attribute_binding": [
            {
                **entity,
                "modeled_attribute_name": "ID",
                "attribute_name": "ID",
                "model_attribute_binding_status": "active",
            }
        ],
    }
    keys = {
        "model_details": [],
        "model_input_scope": OBJECT_FIELDS,
        "logical_entity": ["logical_entity_name"],
        "logical_attribute": ["logical_entity_name", "logical_attribute_name"],
        "model_object_binding": ["modeled_entity_type", "modeled_entity_name"],
        "model_attribute_binding": [
            "modeled_entity_type",
            "modeled_entity_name",
            "modeled_attribute_name",
        ],
    }
    write_graph_snapshot(session, "model", rows, keys)
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Preserve bound evidence",
        "--plan",
        '["Validate"]',
    )
    assert added.returncode == 0, added.stderr
    if rebound:
        (session / "model-change-set/model_object_binding.json").write_text(
            json.dumps([{**binding, "object_name": "OtherCustomer"}])
        )
    arguments = ["validate", "--session", str(session), "--area", "model"]
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
        command, cwd=REPOSITORY_ROOT, text=True, capture_output=True, timeout=30, check=False
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["valid"] is (not rebound)
    if rebound:
        assert any(
            issue["code"] == "model_input_reference_invalid"
            and issue["dataset"] == "model_attribute_binding"
            for issue in output["repairs"]
        )
