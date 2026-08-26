from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from test_gds_readiness import write_ready_snapshots


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPOSITORY_ROOT / "plugins" / "v2" / "gds" / "skills" / "gds"
HELPER = SKILL_ROOT / "scripts" / "gds-local.ps1"
JAVASCRIPT_HELPER = SKILL_ROOT / "scripts" / "gds-local.js"
POWERSHELL_DOCKER_IMAGE = os.environ.get("GDS_POWERSHELL_DOCKER_IMAGE")
POWERSHELL_DOCKER_WRITE_ROOT = os.environ.get("GDS_POWERSHELL_DOCKER_WRITE_ROOT")
WINDOWS_POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")
POWERSHELL_COMMAND = WINDOWS_POWERSHELL or shutil.which("pwsh")
POWERSHELL_AVAILABLE = POWERSHELL_COMMAND is not None or bool(
    POWERSHELL_DOCKER_IMAGE and POWERSHELL_DOCKER_WRITE_ROOT and shutil.which("docker")
)


def run_powershell(*arguments: str) -> subprocess.CompletedProcess[str]:
    if POWERSHELL_DOCKER_IMAGE:
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "pwsh",
            "-v",
            f"{REPOSITORY_ROOT}:{REPOSITORY_ROOT}:ro",
            "-v",
            f"{POWERSHELL_DOCKER_WRITE_ROOT}:{POWERSHELL_DOCKER_WRITE_ROOT}",
            "-w",
            str(REPOSITORY_ROOT),
            POWERSHELL_DOCKER_IMAGE,
            "-NoProfile",
            "-File",
            str(HELPER),
            *arguments,
        ]
    else:
        assert POWERSHELL_COMMAND is not None
        command = [POWERSHELL_COMMAND, "-NoProfile", "-File", str(HELPER), *arguments]
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=120 if POWERSHELL_DOCKER_IMAGE else 60,
        check=False,
    )


def run_javascript(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(JAVASCRIPT_HELPER), *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def write_metadata_snapshot_manifest(
    snapshot: Path,
    snapshot_id: str = "00000000-0000-4000-8000-000000000001",
) -> None:
    members = []
    for file in sorted(path for path in snapshot.rglob("*") if path.is_file()):
        content = file.read_bytes()
        members.append(
            {
                "path": file.relative_to(snapshot).as_posix(),
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    catalog = next(member for member in members if member["path"] == "catalog.json")
    (snapshot / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "metadata",
                "snapshot_id": snapshot_id,
                "tenant_code": "TENANT_A",
                "catalog": {"path": "catalog.json", "sha256": catalog["sha256"]},
                "members": members,
            },
            separators=(",", ":"),
        )
    )


def write_model_snapshot_manifest(snapshot: Path) -> None:
    members = []
    for file in sorted(path for path in snapshot.rglob("*") if path.is_file()):
        content = file.read_bytes()
        members.append(
            {
                "path": file.relative_to(snapshot).as_posix(),
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    catalog = next(member for member in members if member["path"] == "catalog.json")
    (snapshot / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "model",
                "snapshot_id": "00000000-0000-4000-8000-000000000002",
                "model_id": 41,
                "model_name": "Customer Model",
                "model_revision": 3,
                "catalog": {"path": "catalog.json", "sha256": catalog["sha256"]},
                "members": members,
            },
            separators=(",", ":"),
        )
    )


def write_schema_probe_snapshot(session: Path) -> None:
    snapshot = session / "metadata" / "schema-probe"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    (snapshot / "data" / "schema_probe.jsonl").write_text("")
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "metadata",
                "sections": [
                    {
                        "name": "fixture",
                        "datasets": [
                            {
                                "name": "schema_probe",
                                "record_type": "schema_probe",
                                "row_count": 0,
                                "canonical_key": ["name"],
                                "rows_file": "data/schema_probe.jsonl",
                                "schema_file": "schemas/schema_probe.schema.json",
                            }
                        ],
                    }
                ],
            },
            separators=(",", ":"),
        )
    )
    (snapshot / "schemas" / "schema_probe.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "x-gds-change-set-eligible": True,
                "$defs": {"name": {"type": "string", "pattern": r"\S"}},
                "properties": {
                    "name": {"$ref": "#/$defs/name"},
                    "count": {"allOf": [{"type": "integer"}, {"maximum": 1.5}]},
                    "identifier": {"type": "string", "format": "uuid"},
                    "occurred_at": {"type": "string", "format": "date-time"},
                    "choice": {
                        "oneOf": [
                            {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "kind": {"const": "object"},
                                    "source": {"type": "string"},
                                },
                                "required": ["kind", "source"],
                            },
                            {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "kind": {"const": "assertion"},
                                    "record": {"type": "string"},
                                },
                                "required": ["kind", "record"],
                            },
                        ]
                    },
                },
                "required": ["name", "count", "identifier", "occurred_at", "choice"],
            },
            separators=(",", ":"),
        )
    )
    write_metadata_snapshot_manifest(snapshot)


def write_metadata_domain_snapshot(session: Path) -> None:
    snapshot = session / "metadata" / "metadata-domain"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    datasets = [
        {
            "name": "zone_a_object",
            "record_type": "object",
            "row_count": 1,
            "canonical_key": ["key"],
            "rows_file": "data/zone_a_object.jsonl",
            "schema_file": "schemas/zone_a_object.schema.json",
        },
        {
            "name": "zone_b_object",
            "record_type": "object",
            "row_count": 1,
            "canonical_key": ["key"],
            "rows_file": "data/zone_b_object.jsonl",
            "schema_file": "schemas/zone_b_object.schema.json",
        },
        {
            "name": "child",
            "record_type": "child",
            "row_count": 0,
            "canonical_key": ["child_key"],
            "rows_file": "data/child.jsonl",
            "schema_file": "schemas/child.schema.json",
        },
        {
            "name": "loose_unique",
            "record_type": "loose_unique",
            "row_count": 4,
            "canonical_key": ["key"],
            "rows_file": "data/loose_unique.jsonl",
            "schema_file": "schemas/loose_unique.schema.json",
        },
    ]
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "metadata",
                "sections": [{"name": "fixture", "datasets": datasets}],
            },
            separators=(",", ":"),
        )
    )
    (snapshot / "data" / "zone_a_object.jsonl").write_text(
        '{"key":"A","alias":"DUP","is_active":true}\n'
    )
    (snapshot / "data" / "zone_b_object.jsonl").write_text(
        '{"key":"B","alias":"UNIQUE","is_active":true}\n'
    )
    (snapshot / "data" / "child.jsonl").write_text("")
    (snapshot / "data" / "loose_unique.jsonl").write_text(
        "\n".join(
            (
                '{"key":"MISSING"}',
                '{"key":"NULL","alias":null}',
                '{"key":"ARRAY","alias":[1]}',
                '{"key":"SCALAR","alias":1}',
            )
        )
        + "\n"
    )
    object_schema = {
        "type": "object",
        "additionalProperties": False,
        "x-gds-change-set-eligible": True,
        "x-gds-record-type": "object",
        "x-gds-unique-constraints": [["alias"]],
        "properties": {
            "key": {"type": "string"},
            "alias": {"type": "string"},
            "is_active": {"type": "boolean"},
        },
        "required": ["key", "alias", "is_active"],
    }
    for name in ("zone_a_object", "zone_b_object"):
        (snapshot / "schemas" / f"{name}.schema.json").write_text(
            json.dumps(object_schema, separators=(",", ":"))
        )
    (snapshot / "schemas" / "child.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "x-gds-change-set-eligible": True,
                "x-gds-record-type": "child",
                "x-gds-references": [
                    {
                        "columns": ["parent_key"],
                        "target_record_type": "object",
                        "target_columns": ["key"],
                        "nullable": False,
                    }
                ],
                "properties": {
                    "child_key": {"type": "string"},
                    "parent_key": {"type": "string"},
                    "is_active": {"type": "boolean"},
                },
                "required": ["child_key", "parent_key", "is_active"],
            },
            separators=(",", ":"),
        )
    )
    (snapshot / "schemas" / "loose_unique.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "x-gds-change-set-eligible": True,
                "x-gds-record-type": "loose_unique",
                "x-gds-unique-constraints": [["alias"]],
                "properties": {"key": {"type": "string"}, "alias": {}},
                "required": ["key"],
            },
            separators=(",", ":"),
        )
    )
    write_metadata_snapshot_manifest(snapshot)


def write_model_structure_snapshot(session: Path) -> None:
    snapshot = session / "model" / "model-structure"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    assertion_source = {
        "support_source_type": "assertion",
        "assertion_record": {"modeling_assertion_record_key": "A"},
    }
    physical = {
        "tenant_code": "TENANT_A",
        "system_code": "SILVER",
        "connection_code": "MAIN",
        "object_schema": "silver",
        "object_name": "customer",
    }
    records = {
        "modeling_assertion_document": [{"modeling_assertion_document_name": "D"}],
        "modeling_assertion_record": [
            {
                "modeling_assertion_record_key": "A",
                "modeling_assertion_document_name": "D",
                "modeling_assertion_applicable_layers": ["logical", "LOGICAL"],
            }
        ],
        "conceptual_object": [
            {
                "conceptual_object_name": "Customer",
                "conceptual_object_aliases": ["Buyer", " buyer "],
                "supports": [assertion_source, assertion_source],
            }
        ],
        "conceptual_relationship": [
            {
                "conceptual_relationship_name": "Customer owns Missing",
                "from_conceptual_object_name": "Customer",
                "to_conceptual_object_name": "Missing",
                "supports": [],
            }
        ],
        "logical_entity": [
            {
                "logical_entity_name": "Retired",
                "logical_entity_status": "inactive",
                "submodels": [{"submodel_name": "Missing"}],
                "sources": [assertion_source],
            }
        ],
        "logical_attribute": [
            {
                "logical_entity_name": "Retired",
                "logical_attribute_name": "id",
                "sources": [],
            }
        ],
        "logical_relationship": [
            {
                "logical_relationship_name": "Broken",
                "from_logical_entity_name": "Retired",
                "from_logical_attribute_name": "id",
                "to_logical_entity_name": "Missing",
                "to_logical_attribute_name": "id",
            }
        ],
        "mapping_dependency": [],
        "mapping_object": [
            {
                **physical,
                "source_system_code": "CRM",
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Retired",
            }
        ],
        "mapping_attribute": [
            {
                **physical,
                "source_system_code": "CRM",
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Retired",
                "modeled_attribute_name": "id",
            }
        ],
    }
    canonical_keys = {
        "modeling_assertion_document": ["modeling_assertion_document_name"],
        "modeling_assertion_record": ["modeling_assertion_record_key"],
        "conceptual_object": ["conceptual_object_name"],
        "conceptual_relationship": ["conceptual_relationship_name"],
        "logical_entity": ["logical_entity_name"],
        "logical_attribute": ["logical_entity_name", "logical_attribute_name"],
        "logical_relationship": ["logical_relationship_name"],
        "mapping_dependency": ["source_system_code", "modeled_entity_type"],
        "mapping_object": ["object_name", "modeled_entity_name"],
        "mapping_attribute": [
            "object_name",
            "modeled_entity_name",
            "modeled_attribute_name",
        ],
    }
    datasets = []
    for name, values in records.items():
        rows_file = snapshot / "data" / f"{name}.jsonl"
        rows_file.write_text(
            "".join(f"{json.dumps(value, separators=(',', ':'))}\n" for value in values)
        )
        (snapshot / "schemas" / f"{name}.schema.json").write_text(
            '{"x-gds-change-set-eligible":true}'
        )
        datasets.append(
            {
                "name": name,
                "record_type": name,
                "row_count": len(values),
                "canonical_key": canonical_keys[name],
                "rows_file": f"data/{name}.jsonl",
                "schema_file": f"schemas/{name}.schema.json",
            }
        )
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "model",
                "model": {
                    "model_id": 41,
                    "model_name": "Customer Model",
                    "model_revision": 3,
                },
                "sections": [{"name": "fixture", "datasets": datasets}],
            },
            separators=(",", ":"),
        )
    )
    write_model_snapshot_manifest(snapshot)


def write_model_policy_snapshot(session: Path) -> None:
    snapshot = session / "model" / "model-policy"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    records = {
        "analysis_result": [],
        "conceptual_object": [{"conceptual_object_name": "Customer", "supports": []}],
        "conceptual_relationship": [],
        "logical_submodel": [],
        "logical_entity": [
            {
                "logical_entity_name": "Customer",
                "logical_entity_type": "core",
                "logical_entity_type_detail": None,
                "submodels": [],
                "sources": [],
            }
        ],
        "logical_attribute": [
            {
                "logical_entity_name": "Customer",
                "logical_attribute_name": "id",
                "sources": [],
            }
        ],
        "logical_relationship": [],
        "dimensional_submodel": [],
        "dimensional_entity": [
            {
                "dimensional_entity_name": "Sale",
                "dimensional_entity_type": "dimension",
                "dimensional_fact_type": None,
                "dimensional_entity_grain_definition": None,
                "submodels": [],
                "sources": [],
            }
        ],
        "dimensional_attribute": [
            {
                "dimensional_entity_name": "Sale",
                "dimensional_attribute_name": "id",
                "sources": [],
            }
        ],
        "dimensional_relationship": [],
    }
    canonical_keys = {
        "analysis_result": ["relationship_kind"],
        "conceptual_object": ["conceptual_object_name"],
        "conceptual_relationship": ["conceptual_relationship_name"],
        "logical_submodel": ["logical_submodel_name"],
        "logical_entity": ["logical_entity_name"],
        "logical_attribute": ["logical_entity_name", "logical_attribute_name"],
        "logical_relationship": ["logical_relationship_name"],
        "dimensional_submodel": ["dimensional_submodel_name"],
        "dimensional_entity": ["dimensional_entity_name"],
        "dimensional_attribute": [
            "dimensional_entity_name",
            "dimensional_attribute_name",
        ],
        "dimensional_relationship": ["dimensional_relationship_name"],
    }
    datasets = []
    for name, values in records.items():
        (snapshot / "data" / f"{name}.jsonl").write_text(
            "".join(f"{json.dumps(value, separators=(',', ':'))}\n" for value in values)
        )
        (snapshot / "schemas" / f"{name}.schema.json").write_text(
            '{"x-gds-change-set-eligible":true}'
        )
        datasets.append(
            {
                "name": name,
                "record_type": name,
                "row_count": len(values),
                "canonical_key": canonical_keys[name],
                "rows_file": f"data/{name}.jsonl",
                "schema_file": f"schemas/{name}.schema.json",
            }
        )
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "model",
                "model": {
                    "model_id": 41,
                    "model_name": "Customer Model",
                    "model_revision": 3,
                },
                "sections": [{"name": "fixture", "datasets": datasets}],
            },
            separators=(",", ":"),
        )
    )
    write_model_snapshot_manifest(snapshot)


def write_model_scope_snapshot(session: Path) -> None:
    snapshot = session / "model" / "model-scope"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    active = {
        "tenant_code": "TENANT_A",
        "system_code": "RAW",
        "connection_code": "MAIN",
        "object_schema": "raw",
        "object_name": "customer",
    }
    inactive = {**active, "object_name": "order"}
    records = {
        "model_scope": [
            {**active, "is_active": True},
            {**inactive, "is_active": False},
        ],
        "conceptual_object": [
            {"conceptual_object_name": "Customer", "supports": []},
            {"conceptual_object_name": "Order", "supports": []},
        ],
        "conceptual_relationship": [],
        "logical_submodel": [],
        "logical_entity": [
            {
                "logical_entity_name": "Customer",
                "logical_entity_type": "core",
                "logical_entity_type_detail": None,
                "submodels": [],
                "sources": [],
            }
        ],
        "logical_attribute": [
            {
                "logical_entity_name": "Customer",
                "logical_attribute_name": "id",
                "sources": [],
            }
        ],
        "logical_relationship": [],
        "dimensional_submodel": [],
        "dimensional_entity": [
            {
                "dimensional_entity_name": "Sale",
                "dimensional_entity_type": "dimension",
                "dimensional_fact_type": None,
                "dimensional_entity_grain_definition": None,
                "submodels": [],
                "sources": [],
            }
        ],
        "dimensional_attribute": [
            {
                "dimensional_entity_name": "Sale",
                "dimensional_attribute_name": "id",
                "sources": [],
            }
        ],
        "dimensional_relationship": [],
        "profiling_profile": [],
        "analysis_result": [],
        "mapping_dependency": [
            {
                "source_system_code": "CRM",
                "modeled_entity_type": "logical_entity",
            },
            {
                "source_system_code": "SILVER",
                "modeled_entity_type": "dimensional_entity",
            },
        ],
        "mapping_object": [],
        "mapping_attribute": [],
    }
    canonical_keys = {
        "model_scope": [
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        ],
        "conceptual_object": ["conceptual_object_name"],
        "conceptual_relationship": ["conceptual_relationship_name"],
        "logical_submodel": ["logical_submodel_name"],
        "logical_entity": ["logical_entity_name"],
        "logical_attribute": ["logical_entity_name", "logical_attribute_name"],
        "logical_relationship": ["logical_relationship_name"],
        "dimensional_submodel": ["dimensional_submodel_name"],
        "dimensional_entity": ["dimensional_entity_name"],
        "dimensional_attribute": [
            "dimensional_entity_name",
            "dimensional_attribute_name",
        ],
        "dimensional_relationship": ["dimensional_relationship_name"],
        "profiling_profile": ["object_name", "attribute_name"],
        "analysis_result": ["analysis_result_key"],
        "mapping_dependency": ["source_system_code", "modeled_entity_type"],
        "mapping_object": ["object_name", "modeled_entity_name"],
        "mapping_attribute": [
            "object_name",
            "modeled_entity_name",
            "modeled_attribute_name",
        ],
    }
    datasets = []
    for name, values in records.items():
        (snapshot / "data" / f"{name}.jsonl").write_text(
            "".join(f"{json.dumps(value, separators=(',', ':'))}\n" for value in values)
        )
        (snapshot / "schemas" / f"{name}.schema.json").write_text(
            '{"x-gds-change-set-eligible":true}'
        )
        datasets.append(
            {
                "name": name,
                "record_type": name,
                "row_count": len(values),
                "canonical_key": canonical_keys[name],
                "rows_file": f"data/{name}.jsonl",
                "schema_file": f"schemas/{name}.schema.json",
            }
        )
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "model",
                "model": {
                    "model_id": 41,
                    "model_name": "Customer Model",
                    "model_revision": 3,
                },
                "sections": [{"name": "fixture", "datasets": datasets}],
            },
            separators=(",", ":"),
        )
    )
    write_model_snapshot_manifest(snapshot)


def prepare_powershell_accepted_probe(
    tmp_path: Path,
) -> tuple[Path, dict[str, object], str]:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_schema_probe_snapshot(session)
    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Stage probe",
        "--plan",
        '["Edit","Review","Stage","Apply"]',
    )
    assert added.returncode == 0, added.stderr
    record: dict[str, object] = {
        "name": "Probe",
        "count": 1,
        "identifier": "00000000-0000-4000-8000-000000000001",
        "occurred_at": "2026-08-22T00:00:00Z",
        "choice": {"source": "CRM", "kind": "object"},
    }
    upserted = run_powershell(
        "upsert",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "schema_probe",
        "--record",
        json.dumps(record, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    assert upserted.returncode == 0, upserted.stderr
    digest = json.loads(upserted.stdout)["digest"]
    accepted = run_powershell(
        "accept", "--session", str(session), "--area", "metadata", "--digest", digest
    )
    assert accepted.returncode == 0, accepted.stderr
    return session, record, digest


def test_powershell_fallback_is_native_local_only_and_command_compatible() -> None:
    source = HELPER.read_text()
    lowered = source.lower()

    for dependency in (
        "python",
        "node ",
        "node.exe",
        "npm",
        "invoke-webrequest",
        "invoke-restmethod",
    ):
        assert dependency not in lowered
    assert "ConvertFrom-Json" not in source
    assert "ConvertTo-Json" not in source
    assert "namespace Gds.Local" in source
    assert "function ConvertFrom-GdsJson" in source
    assert "function ConvertTo-GdsJson" in source
    assert "new OrderedDictionary(StringComparer.Ordinal)" in source
    assert "$script:JsonMaxDepth = 512" in source
    assert "$draft.Count -ne 5" in source
    assert "function Stash-Task" in source
    assert "function Restore-Task" in source
    assert "generator-document@1.0" in source
    assert "function Test-CurrentGeneratorProof" in source
    assert "function Get-ProofUnits" in source
    assert "--proof-units must contain unique exact target/source pairs." in source
    assert "$ExpectedUnits.Count -eq 0" in source
    assert "cache_bound = [bool]$cacheBound" in source
    for command in (
        "session-init",
        "status",
        "readiness",
        "mapping-proof",
        "generator-proof",
        "draft-cache",
        "inspect",
        "describe",
        "select",
        "task-add",
        "task-plan",
        "task-state",
        "task-stash",
        "task-restore",
        "copy",
        "upsert",
        "upsert-batch",
        "discard",
        "review",
        "validate",
        "accept",
        "snapshot-refresh",
        "reconcile",
    ):
        assert f"'{command}'" in source
    assert "expected-digest" in source
    assert "tasks = @($state.tasks)" in source
    assert "cs = $cache" in source
    assert "ReparsePoint" in source
    assert "WriteAllText" in source
    assert "Snapshot manifest contains duplicate member path" in source
    assert "Snapshot manifest contains an unsafe member path" in source
    assert "Snapshot member size mismatch" in source
    assert "Snapshot member SHA-256 mismatch" in source
    assert "Members = $members" in source
    assert "Assert-SessionSnapshotIdentity" in source
    assert "Metadata Snapshot Tenant Code does not match" in source
    assert "start a new session for Model" in source
    assert "model = $model" in source
    assert "switch -CaseSensitive ($target)" in source
    assert "-cnotcontains $target" in source
    assert "-ceq 'active'" in source
    assert "$active -is [bool]" in source
    assert "Complete and Apply the matching Logical or Dimensional Mapping" in source
    assert "mapping-authoring@1.0" in source
    assert "Test-CurrentMappingProof" in source
    assert "value must match exactly one allowed schema" in source
    assert "exclusiveMinimum" in source
    assert "minItems" in source
    assert "#/$defs/" in source
    assert "Test-JsonSchemaFormat" in source
    assert "if ($property.Name -ceq $Name)" in source
    assert "[math]::Truncate($number) -eq $number" in source
    assert "[Text.RegularExpressions.RegexOptions]::ECMAScript" in source
    assert "[89ab][0-9a-f]{3}" in source
    assert "Test-JsonNumber $maximum" in source


def test_powershell_registration_allows_optional_model_policies_to_be_absent() -> None:
    source = HELPER.read_text()

    assert "silver_model_naming_template" not in source
    assert "gold_model_naming_template" not in source
    assert "'policy_missing'" not in source


def test_powershell_analysis_validation_group_matches_the_runtime_contract() -> None:
    source = HELPER.read_text()

    for field in (
        "validation_policy_version",
        "validation_result",
        "validation_source_non_null_count",
        "validation_source_distinct_count",
        "validation_target_non_null_count",
        "validation_target_distinct_count",
        "validation_source_missing_target_count",
        "validation_unused_target_count",
        "validation_duplicate_target_key_count",
    ):
        assert f"'{field}'" in source
    assert "Analysis validation fields must all be present or all be absent." in source


def test_powershell_readiness_uses_scope_eligibility_flags() -> None:
    source = HELPER.read_text()

    for field in (
        "is_bronze_source_eligible",
        "is_dimensional_source_eligible",
        "is_logical_mapping_target_eligible",
        "is_dimensional_mapping_target_eligible",
    ):
        assert f"'{field}'" in source
    assert "$targetEligibilityField" in source
    assert "$executableEligibilityField" in source
    assert "$eligibleSources" in source


def test_powershell_model_validator_enforces_scope_eligibility() -> None:
    source = HELPER.read_text()

    for message in (
        "Referenced physical Object is not an eligible Bronze source.",
        "Referenced physical Attribute is not an eligible Bronze source.",
        "Referenced physical Object is not an eligible Silver contribution from applied Logical Mapping.",
        "Referenced physical Attribute is not an eligible Silver contribution from applied Logical Mapping.",
        "Referenced Mapping target is not eligible for its modeled layer.",
    ):
        assert message in source


def test_powershell_allows_model_details_but_not_model_scope_mutation() -> None:
    source = HELPER.read_text()

    assert "$Dataset.name -ceq 'model_scope'" in source
    assert "@('model_details', 'model_scope')" not in source


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
@pytest.mark.parametrize("target", ("silver-registration", "gold-registration"))
def test_powershell_registration_optional_policies_match_javascript(
    tmp_path: Path, target: str
) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_ready_snapshots(session, policies_present=False)

    powershell = run_powershell(
        "readiness", "--session", str(session), "--target", target
    )
    javascript = run_javascript(
        "readiness", "--session", str(session), "--target", target
    )

    assert powershell.returncode == 0, powershell.stderr
    assert javascript.returncode == 0, javascript.stderr
    output = json.loads(powershell.stdout)
    assert output["ready"] is True
    assert all(blocker[0] != "policy_missing" for blocker in output["blockers"])
    assert output == json.loads(javascript.stdout)


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
@pytest.mark.parametrize(
    ("target", "settings", "expected_blocker"),
    (
        ("logical-build", {"include_ineligible_scope": True}, None),
        ("logical-mapping", {"logical_target_eligible": False}, "scope_missing"),
        ("logical-mapping", {"bronze_source_eligible": False}, "lineage_missing"),
        (
            "dimensional-mapping",
            {
                "dimensional_source_eligible": False,
                "dimensional_target_eligible": False,
            },
            "scope_missing",
        ),
        (
            "dimensional-build",
            {"dimensional_source_eligible": False},
            "scope_missing",
        ),
    ),
)
def test_powershell_scope_eligibility_matches_javascript(
    tmp_path: Path,
    target: str,
    settings: dict[str, bool],
    expected_blocker: str | None,
) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_ready_snapshots(session, **settings)

    powershell = run_powershell(
        "readiness", "--session", str(session), "--target", target
    )
    javascript = run_javascript(
        "readiness", "--session", str(session), "--target", target
    )

    assert powershell.returncode == 0, powershell.stderr
    assert javascript.returncode == 0, javascript.stderr
    output = json.loads(powershell.stdout)
    blockers = [blocker[0] for blocker in output["blockers"]]
    if expected_blocker is None:
        assert output["ready"] is True
    else:
        assert expected_blocker in blockers
    if target == "dimensional-mapping":
        assert "lineage_missing" in blockers
    assert output == json.loads(javascript.stdout)


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_session_init_matches_javascript_shape(tmp_path: Path) -> None:
    result = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "tenant": "TENANT_A",
        "session": "01",
        "path": str(tmp_path / "GDS" / "TENANT_A" / "01"),
    }


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_status_returns_waiting_task_plan_without_mutation(
    tmp_path: Path,
) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    plan = ["Inputs: metadata=snapshot-01", "Resume selected metadata work"]
    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Waiting metadata task",
        "--plan",
        json.dumps(plan, separators=(",", ":")),
    )
    assert added.returncode == 0, added.stderr
    waiting = run_powershell(
        "task-state", "--session", str(session), "--task", "01", "--state", "waiting"
    )
    assert waiting.returncode == 0, waiting.stderr
    state_path = session / "session.json"
    state_before = state_path.read_bytes()

    status = run_powershell("status", "--session", str(session))

    assert status.returncode == 0, status.stderr
    output = json.loads(status.stdout)
    assert output["current"] is None
    assert output["resume"] == [
        "01",
        "metadata",
        "Waiting metadata task",
        "waiting",
    ]
    assert output["plan"] == plan
    assert output["plan_digest"] == json.loads(added.stdout)["plan_digest"]
    assert output["stashes"] == []
    assert state_path.read_bytes() == state_before


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_codec_round_trips_deep_large_and_case_distinct_state(
    tmp_path: Path,
) -> None:
    session = tmp_path / "GDS" / "TENANT_A" / "01"
    (session / "tasks").mkdir(parents=True)
    (session / "metadata-change-set").mkdir()
    deep: object = "leaf"
    for _ in range(120):
        deep = {"nested": deep}
    probe = {
        "deep": deep,
        "large": "x" * 2_097_153,
        "keys": {"": "empty", "Name": "upper", "name": "lower"},
    }
    state_path = session / "session.json"
    state_path.write_text(
        json.dumps(
            {"current": None, "tasks": [], "probe": probe}, separators=(",", ":")
        )
        + "\n"
    )
    assert len(state_path.read_text()) > 2_097_152

    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Exercise JSON codec",
        "--plan",
        '["Preserve state"]',
    )

    assert added.returncode == 0, added.stderr
    rewritten = json.loads(state_path.read_text())
    assert rewritten["probe"]["large"] == probe["large"]
    assert rewritten["probe"]["keys"] == probe["keys"]
    cursor = rewritten["probe"]["deep"]
    for _ in range(120):
        cursor = cursor["nested"]
    assert cursor == "leaf"


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_codec_preserves_escaped_date_string(tmp_path: Path) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])

    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Preserve date-like string",
        "--plan",
        r'["\/Date(0)\/"]',
    )

    assert added.returncode == 0, added.stderr
    assert json.loads((session / "tasks" / "01.json").read_text()) == ["/Date(0)/"]


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_codec_rejects_non_strict_json(tmp_path: Path) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    state_path = session / "session.json"

    for invalid in (
        "{current:null,tasks:[]}",
        "{'current':null,'tasks':[]}",
        '{"current":null,"tasks":[],"probe":+1}',
        '{"current":null,"tasks":[],"probe":"line\nbreak"}',
    ):
        state_path.write_text(invalid)
        result = run_powershell("status", "--session", str(session))
        assert result.returncode != 0
        assert "Session state is not valid JSON." in result.stderr


@pytest.mark.skipif(
    os.name != "nt" or WINDOWS_POWERSHELL is None,
    reason="Windows PowerShell 5.1 is unavailable",
)
def test_windows_runner_prefers_powershell_51() -> None:
    assert WINDOWS_POWERSHELL is not None
    assert Path(WINDOWS_POWERSHELL).name.lower() == "powershell.exe"
    result = subprocess.run(
        [
            WINDOWS_POWERSHELL,
            "-NoProfile",
            "-Command",
            "[Console]::Out.Write($PSVersionTable.PSEdition + ':' + $PSVersionTable.PSVersion.Major)",
        ],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Desktop:5"


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_snapshot_refresh_retires_only_exact_applied_records(
    tmp_path: Path,
) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_schema_probe_snapshot(session)
    record = {
        "name": "Probe",
        "count": 1,
        "identifier": "00000000-0000-4000-8000-000000000001",
        "occurred_at": "0000-01-01T00:00:00+15:00",
        "choice": {"kind": "object", "source": "CRM"},
    }
    pending = session / "metadata-change-set" / "schema_probe.json"
    pending.write_text(json.dumps([record], separators=(",", ":")) + "\n")
    (session / "session.json").write_text(
        json.dumps(
            {
                "current": None,
                "tasks": [["01", "metadata", "Applied probe", "applied"]],
                "stale": ["metadata"],
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    (session / "tasks" / "01.applied.json").write_text(
        '["metadata","00000000-0000-4000-8000-000000000001",null]\n'
    )
    snapshot = session / "metadata" / "schema-probe"
    (snapshot / "data" / "schema_probe.jsonl").write_text(
        json.dumps(record, separators=(",", ":")) + "\n"
    )
    write_metadata_snapshot_manifest(snapshot, "00000000-0000-4000-8000-000000000003")

    refreshed = run_powershell(
        "snapshot-refresh", "--session", str(session), "--area", "metadata"
    )

    assert refreshed.returncode == 0, refreshed.stderr
    assert json.loads(refreshed.stdout)["retired"] == 1
    assert not pending.exists()
    assert "stale" not in json.loads((session / "session.json").read_text())


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_schema_validation_matches_workbench_contract(
    tmp_path: Path,
) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_schema_probe_snapshot(session)
    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Check schema parity",
        "--plan",
        '["Validate one record"]',
    )
    assert added.returncode == 0, added.stderr

    base = {
        "name": "Probe",
        "count": 1.0,
        "identifier": "00000000-0000-4000-8000-000000000001",
        "occurred_at": "0000-01-01T00:00:00+15:00",
        "choice": {"kind": "object", "source": "CRM"},
    }
    invalid_records = [
        (
            {
                **{key: value for key, value in base.items() if key != "name"},
                "Name": "Probe",
            },
            "required field is missing",
        ),
        ({**base, "count": 2}, "above maximum"),
        ({**base, "identifier": "00000000-0000-0000-0000-000000000000"}, "uuid"),
        ({**base, "name": "\ufeff"}, "fails pattern"),
        (
            {**base, "choice": {"kind": "object", "record": "A-1"}},
            "exactly one allowed schema",
        ),
    ]
    for record, expected in invalid_records:
        result = run_powershell(
            "upsert",
            "--session",
            str(session),
            "--area",
            "metadata",
            "--dataset",
            "schema_probe",
            "--record",
            json.dumps(record, separators=(",", ":")),
            "--expected-digest",
            "empty",
        )
        assert result.returncode != 0
        assert expected in result.stderr

    valid = run_powershell(
        "upsert",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "schema_probe",
        "--record",
        json.dumps(base, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    assert valid.returncode == 0, valid.stderr


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_review_accept_and_reconcile_match_javascript(
    tmp_path: Path,
) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_schema_probe_snapshot(session)
    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Reconcile probe",
        "--plan",
        '["Review","Accept","Reconcile"]',
    )
    assert added.returncode == 0, added.stderr
    record = {
        "name": "Probe",
        "count": 1,
        "identifier": "00000000-0000-4000-8000-000000000001",
        "occurred_at": "0000-01-01T00:00:00+15:00",
        "choice": {"source": "CRM", "kind": "object"},
    }
    upserted = run_powershell(
        "upsert",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "schema_probe",
        "--record",
        json.dumps(record, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    assert upserted.returncode == 0, upserted.stderr

    ps_review = run_powershell(
        "review", "--session", str(session), "--area", "metadata"
    )
    js_review = run_javascript(
        "review", "--session", str(session), "--area", "metadata"
    )
    assert ps_review.returncode == js_review.returncode == 0
    assert json.loads(ps_review.stdout) == json.loads(js_review.stdout)
    digest = json.loads(ps_review.stdout)["digest"]

    ps_accept = run_powershell(
        "accept", "--session", str(session), "--area", "metadata", "--digest", digest
    )
    js_accept = run_javascript(
        "accept", "--session", str(session), "--area", "metadata", "--digest", digest
    )
    assert ps_accept.returncode == js_accept.returncode == 0
    assert json.loads(ps_accept.stdout) == json.loads(js_accept.stdout)

    draft_id = "00000000-0000-4000-8000-000000000123"
    ps_cache = run_powershell(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "1",
        "--status",
        "active",
    )
    js_cache = run_javascript(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "1",
        "--status",
        "active",
    )
    assert ps_cache.returncode == js_cache.returncode == 0
    assert json.loads(ps_cache.stdout) == json.loads(js_cache.stdout)

    server = json.dumps({"schema_probe": [record]}, separators=(",", ":"))
    ps_reconcile = run_powershell(
        "reconcile", "--session", str(session), "--area", "metadata", "--server", server
    )
    js_reconcile = run_javascript(
        "reconcile", "--session", str(session), "--area", "metadata", "--server", server
    )
    assert ps_reconcile.returncode == js_reconcile.returncode == 0
    assert json.loads(ps_reconcile.stdout) == json.loads(js_reconcile.stdout)

    for invalid_server, expected in (
        ({"schema_probe": record}, "must be a JSON array"),
        ({"schema_probe": [{"name": "Probe"}]}, "record is invalid"),
    ):
        for runner in (run_powershell, run_javascript):
            result = runner(
                "reconcile",
                "--session",
                str(session),
                "--area",
                "metadata",
                "--server",
                json.dumps(invalid_server, separators=(",", ":")),
            )
            assert result.returncode != 0
            assert expected in result.stderr


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_cache_clear_staged_reconcile_and_apply_are_digest_bound(
    tmp_path: Path,
) -> None:
    session, record, digest = prepare_powershell_accepted_probe(tmp_path)
    draft_id = "00000000-0000-4000-8000-000000000123"
    cached = run_powershell(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "1",
        "--status",
        "active",
    )
    assert cached.returncode == 0, cached.stderr
    assert json.loads(cached.stdout)["draft"] == [draft_id, 1, "active", "01", digest]

    state_before = (session / "session.json").read_bytes()
    wrong_clear = run_powershell(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--clear",
        "true",
        "--expected-id",
        "00000000-0000-4000-8000-000000000999",
        "--expected-revision",
        "1",
    )
    assert wrong_clear.returncode != 0
    assert "exact cached server draft" in wrong_clear.stderr
    assert (session / "session.json").read_bytes() == state_before

    cleared = run_powershell(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--clear",
        "true",
        "--expected-id",
        draft_id,
        "--expected-revision",
        "1",
    )
    assert cleared.returncode == 0, cleared.stderr
    assert json.loads(cleared.stdout) == {"area": "metadata", "draft": None}
    assert "cs" not in json.loads((session / "session.json").read_text())

    recached = run_powershell(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "1",
        "--status",
        "active",
    )
    assert recached.returncode == 0, recached.stderr
    staged = run_powershell(
        "task-state", "--session", str(session), "--task", "01", "--state", "staged"
    )
    assert staged.returncode == 0, staged.stderr

    reconciled = run_powershell(
        "reconcile",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--server",
        json.dumps({"schema_probe": [record]}, separators=(",", ":")),
    )
    assert reconciled.returncode == 0, reconciled.stderr
    assert json.loads(reconciled.stdout)["cache_bound"] is True

    active_apply = run_powershell(
        "task-state", "--session", str(session), "--task", "01", "--state", "applied"
    )
    assert active_apply.returncode != 0
    assert "must be validated" in active_apply.stderr
    assert json.loads((session / "session.json").read_text())["tasks"][0][3] == "staged"

    validated = run_powershell(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "2",
        "--status",
        "validated",
    )
    assert validated.returncode == 0, validated.stderr
    regressed = run_powershell(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "2",
        "--status",
        "active",
    )
    assert regressed.returncode != 0
    assert "status cannot regress" in regressed.stderr
    applied = run_powershell(
        "task-state", "--session", str(session), "--task", "01", "--state", "applied"
    )
    assert applied.returncode == 0, applied.stderr
    state = json.loads((session / "session.json").read_text())
    assert state["current"] is None
    assert state["tasks"][0][3] == "applied"
    assert state["stale"] == ["metadata"]
    assert "cs" not in state


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_cache_advances_digest_only_with_newer_active_revision(
    tmp_path: Path,
) -> None:
    session, record, first_digest = prepare_powershell_accepted_probe(tmp_path)
    draft_id = "00000000-0000-4000-8000-000000000123"
    cached = run_powershell(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "1",
        "--status",
        "active",
    )
    assert cached.returncode == 0, cached.stderr

    changed = {**record, "count": 0}
    upserted = run_powershell(
        "upsert",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "schema_probe",
        "--record",
        json.dumps(changed, separators=(",", ":")),
        "--expected-digest",
        first_digest,
    )
    assert upserted.returncode == 0, upserted.stderr
    second_digest = json.loads(upserted.stdout)["digest"]
    assert second_digest != first_digest
    accepted = run_powershell(
        "accept",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--digest",
        second_digest,
    )
    assert accepted.returncode == 0, accepted.stderr

    server = json.dumps({"schema_probe": [changed]}, separators=(",", ":"))
    before_rebind = run_powershell(
        "reconcile", "--session", str(session), "--area", "metadata", "--server", server
    )
    assert before_rebind.returncode == 0, before_rebind.stderr
    assert json.loads(before_rebind.stdout)["cache_bound"] is False

    for revision, status in (("1", "active"), ("2", "validated")):
        rejected = run_powershell(
            "draft-cache",
            "--session",
            str(session),
            "--area",
            "metadata",
            "--id",
            draft_id,
            "--revision",
            revision,
            "--status",
            status,
        )
        assert rejected.returncode != 0
        assert "newer active Stage revision" in rejected.stderr

    rebound = run_powershell(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "2",
        "--status",
        "active",
    )
    assert rebound.returncode == 0, rebound.stderr
    assert json.loads(rebound.stdout)["draft"][-1] == second_digest
    after_rebind = run_powershell(
        "reconcile", "--session", str(session), "--area", "metadata", "--server", server
    )
    assert after_rebind.returncode == 0, after_rebind.stderr
    assert json.loads(after_rebind.stdout)["cache_bound"] is True

    decreased = run_powershell(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--id",
        draft_id,
        "--revision",
        "1",
        "--status",
        "active",
    )
    assert decreased.returncode != 0
    assert "revision cannot decrease" in decreased.stderr


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_task_stash_restore_and_live_set_guards(tmp_path: Path) -> None:
    session, record, first_digest = prepare_powershell_accepted_probe(tmp_path)
    for target in ("waiting", "cancelled"):
        blocked = run_powershell(
            "task-state", "--session", str(session), "--task", "01", "--state", target
        )
        assert blocked.returncode != 0
        assert "task-stash" in blocked.stderr

    wrong = run_powershell(
        "task-stash",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        "0" * 64,
    )
    assert wrong.returncode != 0
    assert "digest conflict" in wrong.stderr

    stashed = run_powershell(
        "task-stash",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        first_digest,
    )
    assert stashed.returncode == 0, stashed.stderr
    assert json.loads(stashed.stdout) == {
        "task": "01",
        "area": "metadata",
        "digest": first_digest,
        "files": 1,
    }
    status = json.loads(run_powershell("status", "--session", str(session)).stdout)
    assert status["stashes"] == [["01", "metadata", 1, first_digest]]
    bypass = run_powershell(
        "task-state", "--session", str(session), "--task", "01", "--state", "doing"
    )
    assert bypass.returncode != 0
    assert "task-restore" in bypass.stderr

    second = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Other probe",
        "--plan",
        '["Edit","Stash"]',
    )
    assert second.returncode == 0, second.stderr
    other = {
        **record,
        "name": "Other",
        "identifier": "00000000-0000-4000-8000-000000000002",
    }
    upserted = run_powershell(
        "upsert",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--dataset",
        "schema_probe",
        "--record",
        json.dumps(other, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )
    assert upserted.returncode == 0, upserted.stderr
    second_digest = json.loads(upserted.stdout)["digest"]
    second_stash = run_powershell(
        "task-stash",
        "--session",
        str(session),
        "--task",
        "02",
        "--expected-digest",
        second_digest,
    )
    assert second_stash.returncode == 0, second_stash.stderr

    unexpected = session / "metadata-change-set" / "unexpected.json"
    unexpected.write_text("[]\n")
    nonempty = run_powershell(
        "task-restore",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        first_digest,
    )
    assert nonempty.returncode != 0
    assert "Local Change Set must be empty" in nonempty.stderr
    unexpected.unlink()

    restored = run_powershell(
        "task-restore",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        first_digest,
    )
    assert restored.returncode == 0, restored.stderr
    status = json.loads(run_powershell("status", "--session", str(session)).stdout)
    assert status["current"] == ["01", "metadata", "Stage probe", "doing"]
    assert status["stashes"] == [["02", "metadata", 1, second_digest]]


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_restore_and_add_reject_stale_or_orphaned_sets(
    tmp_path: Path,
) -> None:
    stale_session = tmp_path / "stale" / "GDS" / "TENANT_A" / "01"
    (stale_session / "tasks" / "01" / "metadata-change-set").mkdir(parents=True)
    (stale_session / "session.json").write_text(
        json.dumps(
            {
                "current": None,
                "tasks": [["01", "metadata", "Stale task", "waiting"]],
                "stale": ["metadata"],
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    stale = run_powershell(
        "task-restore",
        "--session",
        str(stale_session),
        "--task",
        "01",
        "--expected-digest",
        "0" * 64,
    )
    assert stale.returncode != 0
    assert "Snapshot is stale" in stale.stderr

    orphan_session = tmp_path / "orphan" / "GDS" / "TENANT_A" / "01"
    (orphan_session / "tasks").mkdir(parents=True)
    (orphan_session / "metadata-change-set").mkdir()
    (orphan_session / "metadata-change-set" / "schema_probe.json").write_text("[]\n")
    (orphan_session / "session.json").write_text(
        json.dumps(
            {
                "current": None,
                "tasks": [["01", "metadata", "Orphan task", "waiting"]],
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    union = run_powershell(
        "task-add",
        "--session",
        str(orphan_session),
        "--area",
        "metadata",
        "--title",
        "Unsafe union",
        "--plan",
        '["Do not mix"]',
    )
    assert union.returncode != 0
    assert "not task-bound" in union.stderr


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_task_stash_rejects_reparse_parent_without_moving_live_set(
    tmp_path: Path,
) -> None:
    session = tmp_path / "GDS" / "TENANT_A" / "01"
    (session / "tasks").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (session / "tasks" / "01").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")
    live = session / "metadata-change-set"
    live.mkdir()
    pending = b"[]\n"
    pending_path = live / "schema_probe.json"
    pending_path.write_bytes(pending)
    digest = hashlib.sha256(
        pending_path.name.encode()
        + b"\0"
        + str(len(pending)).encode()
        + b"\0"
        + pending
    ).hexdigest()
    (session / "session.json").write_text(
        json.dumps(
            {
                "current": "01",
                "tasks": [["01", "metadata", "Unsafe stash", "doing"]],
            },
            separators=(",", ":"),
        )
        + "\n"
    )

    result = run_powershell(
        "task-stash",
        "--session",
        str(session),
        "--task",
        "01",
        "--expected-digest",
        digest,
    )

    assert result.returncode != 0
    assert "Task stash parent must be a regular directory" in result.stderr
    assert pending_path.read_bytes() == pending
    assert list(outside.iterdir()) == []


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_metadata_validation_uses_effective_records(tmp_path: Path) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_domain_snapshot(session)
    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Check Metadata validation",
        "--plan",
        '["Validate effective records"]',
    )
    assert added.returncode == 0, added.stderr

    digest = "empty"
    records = [
        ("zone_b_object", {"key": "B2", "alias": "DUP", "is_active": True}),
        ("zone_b_object", {"key": "B3", "alias": "UNIQUE", "is_active": True}),
        ("child", {"child_key": "C1", "parent_key": "MISSING", "is_active": True}),
    ]
    for dataset, record in records:
        result = run_powershell(
            "upsert",
            "--session",
            str(session),
            "--area",
            "metadata",
            "--dataset",
            dataset,
            "--record",
            json.dumps(record, separators=(",", ":")),
            "--expected-digest",
            digest,
        )
        assert result.returncode == 0, result.stderr
        digest = json.loads(result.stdout)["digest"]

    validated = run_powershell(
        "validate", "--session", str(session), "--area", "metadata"
    )
    assert validated.returncode == 0, validated.stderr
    output = json.loads(validated.stdout)
    messages = [issue[2] for issue in output["issues"]]
    assert output["valid"] is False
    assert any(
        "Effective records duplicate (alias)." in message for message in messages
    )
    assert any(
        "Effective zone datasets duplicate (alias)." in message for message in messages
    )
    assert any("broken_reference" in message for message in messages)
    if shutil.which("node"):
        javascript = run_javascript(
            "validate", "--session", str(session), "--area", "metadata"
        )
        assert javascript.returncode == 0, javascript.stderr
        assert json.loads(javascript.stdout) == output


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_batch_upsert_writes_multiple_datasets_once(tmp_path: Path) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_metadata_domain_snapshot(session)
    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--title",
        "Batch Metadata",
        "--plan",
        '["Add parent and child"]',
    )
    assert added.returncode == 0, added.stderr
    parent = {"key": "z", "alias": "NEW", "is_active": True}
    unicode_parent = {"key": "ä", "alias": "OTHER", "is_active": True}
    changes = {
        "zone_b_object": [unicode_parent, parent],
        "child": [{"child_key": "C1", "parent_key": "z", "is_active": True}],
    }

    invalid = run_powershell(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--changes",
        json.dumps(
            {
                "child": changes["child"],
                "zone_b_object": [{"key": "z", "is_active": True}],
            },
            separators=(",", ":"),
        ),
        "--expected-digest",
        "empty",
    )
    assert invalid.returncode != 0
    assert "zone_b_object batch record 1 is invalid" in invalid.stderr
    assert list((session / "metadata-change-set").iterdir()) == []
    assert json.loads((session / "session.json").read_text())["tasks"][0][3] == "doing"

    result = run_powershell(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "metadata",
        "--changes",
        json.dumps(changes, separators=(",", ":")),
        "--expected-digest",
        "empty",
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["datasets"] == [["child", 1, 1], ["zone_b_object", 2, 2]]
    assert output["records"] == 3
    assert len(output["digest"]) == 64
    assert [
        record["key"]
        for record in json.loads(
            (session / "metadata-change-set" / "zone_b_object.json").read_text()
        )
    ] == ["z", "ä"]
    powershell = run_powershell(
        "validate", "--session", str(session), "--area", "metadata"
    )
    assert powershell.returncode == 0, powershell.stderr
    assert json.loads(powershell.stdout)["valid"] is True
    if shutil.which("node"):
        javascript = run_javascript(
            "validate", "--session", str(session), "--area", "metadata"
        )
        assert javascript.returncode == 0, javascript.stderr
        assert json.loads(javascript.stdout) == json.loads(powershell.stdout)


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_model_structure_validation_matches_javascript(
    tmp_path: Path,
) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_model_structure_snapshot(session)
    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Check Model structure",
        "--plan",
        '["Validate effective graph"]',
    )
    assert added.returncode == 0, added.stderr

    validated = run_powershell("validate", "--session", str(session), "--area", "model")
    assert validated.returncode == 0, validated.stderr
    output = json.loads(validated.stdout)
    messages = [issue[2] for issue in output["issues"]]
    assert output["valid"] is False
    assert sum("duplicate_nested_key" in message for message in messages) == 3
    assert sum("assertion_layer_invalid" in message for message in messages) == 2
    assert (
        len([issue for issue in output["issues"] if issue[0] == "mapping_object"]) == 1
    )
    assert (
        len([issue for issue in output["issues"] if issue[0] == "logical_relationship"])
        == 1
    )
    if shutil.which("node"):
        javascript = run_javascript(
            "validate", "--session", str(session), "--area", "model"
        )
        assert javascript.returncode == 0, javascript.stderr
        assert json.loads(javascript.stdout) == output


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_model_record_policies_match_javascript(tmp_path: Path) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_model_policy_snapshot(session)
    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Check Model policies",
        "--plan",
        '["Validate changed records"]',
    )
    assert added.returncode == 0, added.stderr

    changed_records = [
        (
            "analysis_result",
            {
                "from_tenant_code": "TENANT_A",
                "from_system_code": "RAW",
                "from_connection_code": "MAIN",
                "from_object_schema": "raw",
                "from_object_name": "customer",
                "from_attribute_name": "customer_id",
                "to_tenant_code": "TENANT_A",
                "to_system_code": "RAW",
                "to_connection_code": "MAIN",
                "to_object_schema": "raw",
                "to_object_name": "order",
                "to_attribute_name": "customer_id",
                "relationship_kind": "partial_validation",
                "validation_policy_version": "1.0.0",
                "analysis_result_status": "active",
                "analysis_result_is_locked": False,
            },
        ),
        (
            "analysis_result",
            {
                "from_tenant_code": "TENANT_A",
                "from_system_code": "RAW",
                "from_connection_code": "MAIN",
                "from_object_schema": "raw",
                "from_object_name": "customer",
                "from_attribute_name": "customer_id",
                "to_tenant_code": "TENANT_A",
                "to_system_code": "RAW",
                "to_connection_code": "MAIN",
                "to_object_schema": "raw",
                "to_object_name": "order",
                "to_attribute_name": "order_id",
                "relationship_kind": "inference_only",
                "analysis_result_status": "active",
                "analysis_result_is_locked": False,
            },
        ),
        (
            "conceptual_relationship",
            {
                "conceptual_relationship_name": "Self",
                "from_conceptual_object_name": "Customer",
                "to_conceptual_object_name": " customer ",
                "supports": [],
            },
        ),
        (
            "logical_entity",
            {
                "logical_entity_name": "Customer",
                "logical_entity_type": "other",
                "logical_entity_type_detail": None,
                "submodels": [],
                "sources": [],
            },
        ),
        (
            "logical_attribute",
            {
                "logical_entity_name": "Customer",
                "logical_attribute_name": "id",
                "logical_attribute_is_natural_key": True,
                "logical_attribute_is_surrogate_key": True,
                "logical_attribute_is_primary_key": True,
                "logical_attribute_is_nullable": True,
                "sources": [],
            },
        ),
        (
            "logical_relationship",
            {
                "logical_relationship_name": "Self",
                "from_logical_entity_name": "Customer",
                "from_logical_attribute_name": "id",
                "to_logical_entity_name": " customer ",
                "to_logical_attribute_name": "ID",
            },
        ),
        (
            "dimensional_entity",
            {
                "dimensional_entity_name": "Sale",
                "dimensional_entity_type": "fact",
                "dimensional_fact_type": None,
                "dimensional_entity_grain_definition": None,
                "submodels": [],
                "sources": [],
            },
        ),
        (
            "dimensional_attribute",
            {
                "dimensional_entity_name": "Sale",
                "dimensional_attribute_name": "id",
                "dimensional_attribute_key_role": "primary",
                "dimensional_attribute_role": "attribute",
                "dimensional_attribute_additivity": "additive",
                "dimensional_attribute_default_aggregation": None,
                "dimensional_attribute_aggregation_basis": None,
                "dimensional_attribute_is_audit_column": True,
                "sources": [],
            },
        ),
        (
            "dimensional_relationship",
            {
                "dimensional_relationship_name": "Self",
                "from_dimensional_entity_name": "Sale",
                "from_dimensional_attribute_name": "id",
                "to_dimensional_entity_name": " sale ",
                "to_dimensional_attribute_name": "ID",
            },
        ),
    ]
    digest = "empty"
    for dataset, record in changed_records:
        result = run_powershell(
            "upsert",
            "--session",
            str(session),
            "--area",
            "model",
            "--dataset",
            dataset,
            "--record",
            json.dumps(record, separators=(",", ":")),
            "--expected-digest",
            digest,
        )
        assert result.returncode == 0, result.stderr
        digest = json.loads(result.stdout)["digest"]

    validated = run_powershell("validate", "--session", str(session), "--area", "model")
    assert validated.returncode == 0, validated.stderr
    output = json.loads(validated.stdout)
    assert output["valid"] is False
    assert sum("record_policy_invalid" in issue[2] for issue in output["issues"]) == 10
    analysis_policy_issues = [
        issue
        for issue in output["issues"]
        if issue[0] == "analysis_result" and "record_policy_invalid" in issue[2]
    ]
    assert len(analysis_policy_issues) == 1
    assert "all be present or all be absent" in analysis_policy_issues[0][2]
    if shutil.which("node"):
        javascript = run_javascript(
            "validate", "--session", str(session), "--area", "model"
        )
        assert javascript.returncode == 0, javascript.stderr
        assert json.loads(javascript.stdout) == output


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_model_physical_scope_matches_javascript(tmp_path: Path) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_model_scope_snapshot(session)
    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Check Model Scope",
        "--plan",
        '["Validate physical references"]',
    )
    assert added.returncode == 0, added.stderr

    active = {
        "tenant_code": "TENANT_A",
        "system_code": "RAW",
        "connection_code": "MAIN",
        "object_schema": "raw",
        "object_name": "customer",
    }
    inactive = {**active, "object_name": "order"}
    object_source = {"support_source_type": "object", "source_object": inactive}
    attribute_source = {
        "support_source_type": "attribute",
        "source_attribute": {**inactive, "attribute_name": "id"},
    }
    records = [
        (
            "conceptual_object",
            {"conceptual_object_name": "Customer", "supports": [object_source]},
        ),
        (
            "conceptual_relationship",
            {
                "conceptual_relationship_name": "Customer Order",
                "from_conceptual_object_name": "Customer",
                "to_conceptual_object_name": "Order",
                "supports": [object_source],
            },
        ),
        (
            "logical_entity",
            {
                "logical_entity_name": "Customer",
                "logical_entity_type": "core",
                "logical_entity_type_detail": None,
                "submodels": [],
                "sources": [object_source],
            },
        ),
        (
            "logical_attribute",
            {
                "logical_entity_name": "Customer",
                "logical_attribute_name": "id",
                "sources": [attribute_source],
            },
        ),
        (
            "dimensional_entity",
            {
                "dimensional_entity_name": "Sale",
                "dimensional_entity_type": "dimension",
                "dimensional_fact_type": None,
                "dimensional_entity_grain_definition": None,
                "submodels": [],
                "sources": [object_source],
            },
        ),
        (
            "dimensional_attribute",
            {
                "dimensional_entity_name": "Sale",
                "dimensional_attribute_name": "id",
                "dimensional_attribute_key_role": "none",
                "dimensional_attribute_role": "attribute",
                "dimensional_attribute_additivity": None,
                "dimensional_attribute_default_aggregation": None,
                "dimensional_attribute_aggregation_basis": None,
                "dimensional_attribute_is_audit_column": False,
                "sources": [attribute_source],
            },
        ),
        (
            "profiling_profile",
            {
                **inactive,
                "attribute_name": "id",
                "non_null_count": 10,
                "null_count": 0,
                "row_count": 10,
                "blank_count": 0,
                "distinct_count": 10,
                "min_data_length": 1,
                "max_data_length": 2,
            },
        ),
        (
            "analysis_result",
            {
                "analysis_result_key": "A1",
                **{f"from_{key}": value for key, value in active.items()},
                "from_attribute_name": "id",
                **{f"to_{key}": value for key, value in inactive.items()},
                "to_attribute_name": "id",
            },
        ),
        (
            "mapping_object",
            {
                **inactive,
                "source_system_code": "CRM",
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Customer",
            },
        ),
        (
            "mapping_attribute",
            {
                **inactive,
                "source_system_code": "CRM",
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Customer",
                "modeled_attribute_name": "id",
            },
        ),
    ]
    digest = "empty"
    for dataset, record in records:
        result = run_powershell(
            "upsert",
            "--session",
            str(session),
            "--area",
            "model",
            "--dataset",
            dataset,
            "--record",
            json.dumps(record, separators=(",", ":")),
            "--expected-digest",
            digest,
        )
        assert result.returncode == 0, result.stderr
        digest = json.loads(result.stdout)["digest"]

    validated = run_powershell("validate", "--session", str(session), "--area", "model")
    assert validated.returncode == 0, validated.stderr
    output = json.loads(validated.stdout)
    assert output["valid"] is False
    assert (
        sum("model_scope_reference_invalid" in issue[2] for issue in output["issues"])
        == 10
    )
    if shutil.which("node"):
        javascript = run_javascript(
            "validate", "--session", str(session), "--area", "model"
        )
        assert javascript.returncode == 0, javascript.stderr
        assert json.loads(javascript.stdout) == output


@pytest.mark.skipif(
    not POWERSHELL_AVAILABLE, reason="PowerShell runtime is unavailable"
)
def test_powershell_remaining_model_record_policies_match_javascript(
    tmp_path: Path,
) -> None:
    initialized = run_powershell(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    write_model_scope_snapshot(session)
    added = run_powershell(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Check remaining Model policies",
        "--plan",
        '["Validate profiling, analysis, and mapping policies"]',
    )
    assert added.returncode == 0, added.stderr

    physical = {
        "tenant_code": "TENANT_A",
        "system_code": "RAW",
        "connection_code": "MAIN",
        "object_schema": "raw",
        "object_name": "customer",
    }
    profiling = {
        **physical,
        "attribute_name": "id",
        "non_null_count": 8,
        "null_count": 3,
        "row_count": 10,
        "blank_count": 9,
        "distinct_count": 9,
        "min_data_length": 5,
        "max_data_length": 2,
    }
    analysis = {
        "analysis_result_key": "A1",
        **{f"from_{key}": value for key, value in physical.items()},
        "from_attribute_name": "id",
        **{f"to_{key}": value for key, value in physical.items()},
        "to_attribute_name": "ID",
    }
    mapping_object = {
        **physical,
        "source_system_code": "CRM",
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": "Customer",
        "artifact_type": "sql",
        "mapping_package_document": "x" * 524_287,
        "object_mapping_transformation_document": {
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "payload": "x" * 262_144,
        },
    }
    mapping_attribute = {
        **physical,
        "source_system_code": "CRM",
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": "Customer",
        "modeled_attribute_name": "id",
        "attribute_mapping_transformation_document": {
            "schema_version": "1.0",
            "transformation_kind": "expression",
            "payload": "x" * 65_536,
        },
    }
    package_overhead = len(
        json.dumps({"payload": ""}, ensure_ascii=False, separators=(",", ":")).encode()
    )
    exact_package = {"payload": "<" * (524_288 - package_overhead)}
    assert (
        len(
            json.dumps(
                exact_package, ensure_ascii=False, separators=(",", ":")
            ).encode()
        )
        == 524_288
    )
    dimensional_mapping_object = {
        **physical,
        "source_system_code": "SILVER",
        "modeled_entity_type": "dimensional_entity",
        "modeled_entity_name": "Sale",
        "artifact_type": "sql",
        "artifact_generation_instructions": "Generate SQL.",
        "mapping_profile_key": "mapping.standard",
        "mapping_profile_version": "1.0.0",
        "mapping_package_document": exact_package,
        "object_mapping_transformation_document": {
            "schema_version": "1.0",
            "transformation_kind": "direct",
        },
    }
    deep_payload: dict[str, object] = {"payload": "x" * 65_536}
    for _ in range(110):
        deep_payload = {"nested": deep_payload}
    deep_transformation = {
        "schema_version": "1.0",
        "transformation_kind": "expression",
        "document": deep_payload,
    }
    dimensional_mapping_attribute = {
        **physical,
        "source_system_code": "SILVER",
        "modeled_entity_type": "dimensional_entity",
        "modeled_entity_name": "Sale",
        "modeled_attribute_name": "id",
        "attribute_mapping_transformation_document": deep_transformation,
    }
    invalid_version_mapping_attribute = {
        **physical,
        "source_system_code": "CRM",
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": "Customer",
        "modeled_attribute_name": "other",
        "attribute_mapping_transformation_document": {
            "schema_version": 1.0,
            "transformation_kind": "expression",
        },
    }
    change_set = session / "model-change-set"
    pending = {
        "profiling_profile": [profiling],
        "analysis_result": [analysis],
        "mapping_object": [mapping_object, dimensional_mapping_object],
        "mapping_attribute": [
            mapping_attribute,
            dimensional_mapping_attribute,
            invalid_version_mapping_attribute,
        ],
    }
    for dataset, records in pending.items():
        (change_set / f"{dataset}.json").write_text(
            json.dumps(records, separators=(",", ":"))
        )

    validated = run_powershell("validate", "--session", str(session), "--area", "model")
    assert validated.returncode == 0, validated.stderr
    output = json.loads(validated.stdout)
    assert output["valid"] is False
    assert sum("record_policy_invalid" in issue[2] for issue in output["issues"]) == 8
    if shutil.which("node"):
        javascript = run_javascript(
            "validate", "--session", str(session), "--area", "model"
        )
        assert javascript.returncode == 0, javascript.stderr
        assert json.loads(javascript.stdout) == output
