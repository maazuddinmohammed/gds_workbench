"""Nonempty server contracts survive local authoring, repair, and Stage preparation."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph
from gds_etl_workbench.domain.snapshots.metadata import DATASETS
from gds_etl_workbench.domain.snapshots.model import model_snapshot_records
from gds_etl_workbench.tools.snapshots.metadata.archive import (
    build_snapshot_archive,
    encode_dataset,
)
from gds_etl_workbench.tools.snapshots.model.archive import build_model_snapshot_archive

from tests.mcp.model_test_fixtures import (
    complete_model_graph,
    complete_physical_scope,
    snapshot_from_graph,
)
from tests.plugin_v2.test_local_validation_parity import install, run_helper


def test_complete_graph_survives_local_authoring_and_repair(tmp_path: Path) -> None:
    physical = complete_physical_scope()
    graph = complete_model_graph()
    snapshot = snapshot_from_graph(graph).model_copy(update={"model_tenant_code": "TENANT-A"})
    canonical = {
        name: [row.model_dump(mode="json") for row in rows]
        for name, rows in model_snapshot_records(snapshot).items()
    }
    # Real exported schemas and rows, including nested supports and optional fields.
    metadata: dict[str, list[dict[str, object]]] = {
        "project": [
            {
                "project_code": "P",
                "project_name": "Sales",
                "project_description": None,
                "is_active": True,
            }
        ],
        "system_type": [
            {
                "system_type_code": "DATABASE",
                "system_type_name": "Database",
                "system_type_description": None,
                "is_active": True,
            }
        ],
        "connection_type": [
            {
                "connection_type_code": "DATABASE",
                "connection_type_name": "Database",
                "connection_type_description": None,
                "is_active": True,
            }
        ],
        "object_type": [
            {
                "object_type_code": "TABLE",
                "object_type_name": "Table",
                "object_type_description": None,
                "is_active": True,
            }
        ],
        "zone": [
            {"zone_code": zone, "zone_name": zone, "zone_description": None, "is_active": True}
            for zone in ("source", "bronze", "silver", "gold")
        ],
        "connection": [
            {
                "tenant_code": tenant,
                "system_code": system,
                "connection_code": connection,
                "connection_name": connection,
                "connection_type_code": "DATABASE",
                "has_foreign_catalog": connection == "fc",
                "foreign_catalog": "source" if connection == "fc" else None,
                "is_global_data_store": connection == "lakehouse",
                "is_active": True,
            }
            for tenant, system, connection in sorted({key[:3] for key in physical.objects})
        ],
        "system": [
            {
                "system_code": code,
                "system_name": code,
                "system_description": None,
                "system_type_code": "DATABASE",
                "is_active": True,
            }
            for code in ("ERP", "GDS")
        ],
        "tenant": [
            {
                "tenant_code": code,
                "tenant_name": code,
                "project_code": "P",
                "tenant_description": None,
                "tenant_catalog": "main",
                "gds_admin_catalog": "admin",
                "gds_connection_tenant_code": "GDS",
                "gds_connection_system_code": "GDS",
                "gds_connection_code": "LAKEHOUSE",
                "tenant_visibility": "private",
                "is_active": True,
            }
            for code in ("TENANT-A", "GDS")
        ],
    }
    for key in sorted(physical.objects):
        zone = "source" if key[3] == "src" else key[3]
        identity = dict(
            zip(
                ("tenant_code", "system_code", "connection_code", "object_schema", "object_name"),
                key,
                strict=True,
            )
        )
        metadata.setdefault(f"{zone}_object", []).append(
            {
                **identity,
                "source_tenant_code": "TENANT-A",
                "zone_code": zone,
                "fc_object_schema": key[3] if zone == "source" else None,
                "fc_object_name": key[4] if zone == "source" else None,
                "object_transformation": None,
                "object_description": "Registered sales data.",
                "batch_attribute_name": None,
                "object_type_code": "TABLE",
                "is_locked": False,
                "is_active": True,
            }
        )
        for ordinal, attr in enumerate(sorted(a for a in physical.attributes if a[:5] == key), 1):
            metadata.setdefault(f"{zone}_attribute", []).append(
                {
                    **identity,
                    "attribute_name": attr[5],
                    "fc_attribute_name": attr[5] if zone == "source" else None,
                    "attribute_ordinal_position": ordinal,
                    "attribute_description": "Stable identifier within the source System.",
                    "attribute_data_type": "STRING" if zone == "bronze" else "BIGINT",
                    "attribute_inferred_data_type": "BIGINT",
                    "attribute_nullability": False,
                    "attribute_custom_code": None,
                    "is_surrogate_key": False,
                    "is_natural_key": False,
                    "is_meta_data": False,
                    "is_masking_required": False,
                    "is_mapped": False,
                    "is_purge": False,
                    "is_locked": False,
                    "is_active": True,
                }
            )
    created = datetime.now(UTC)
    metadata_id, model_id = uuid4(), uuid4()
    metadata_zip, model_zip = tmp_path / "metadata.zip", tmp_path / "model.zip"
    build_snapshot_archive(
        metadata_zip,
        snapshot_id=metadata_id,
        tenant_code="TENANT-A",
        created_time=created,
        available_until=created + timedelta(hours=1),
        encoded_datasets=tuple(encode_dataset(d, metadata.get(d.name, [])) for d in DATASETS),
        max_archive_bytes=16 * 1024 * 1024,
    )
    build_model_snapshot_archive(
        model_zip,
        snapshot_id=model_id,
        snapshot=snapshot,
        created_time=created,
        available_until=created + timedelta(hours=1),
        max_archive_bytes=16 * 1024 * 1024,
    )
    initialized = run_helper("session-init", "--root", str(tmp_path), "--tenant", "TENANT-A")
    assert initialized.returncode == 0
    session = Path(json.loads(initialized.stdout)["path"])
    install(session, "metadata", metadata_zip, str(metadata_id))
    install(session, "model", model_zip, str(model_id))
    added = run_helper(
        "task-add",
        "--session",
        str(session),
        "--area",
        "model",
        "--title",
        "Review complete sales model",
        "--plan",
        '["Validate all families"]',
    )
    assert added.returncode == 0
    saved = run_helper(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "model",
        "--changes",
        json.dumps(canonical),
        "--expected-digest",
        "empty",
    )
    assert saved.returncode == 0, saved.stderr
    digest = json.loads(saved.stdout)["digest"]
    result = run_helper("validate", "--session", str(session), "--area", "model")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["valid"] is True, json.loads(result.stdout)["issues"]
    assert validate_future_graph(
        snapshot=snapshot, physical_scope=physical, staged_documents=canonical
    ).valid

    # A syntactically valid edit can still break the graph. Local and server checks
    # must both catch a retired parent while its Mapping remains active.
    broken = deepcopy(canonical)
    broken["model_object_binding"][0]["model_object_binding_status"] = "inactive"
    changed = run_helper(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "model",
        "--changes",
        json.dumps(broken),
        "--expected-digest",
        digest,
    )
    assert changed.returncode == 0, changed.stderr
    rejected = run_helper("validate", "--session", str(session), "--area", "model")
    assert json.loads(rejected.stdout)["valid"] is False
    assert not validate_future_graph(
        snapshot=snapshot, physical_scope=physical, staged_documents=broken
    ).valid
    repaired = run_helper(
        "upsert-batch",
        "--session",
        str(session),
        "--area",
        "model",
        "--changes",
        json.dumps(canonical),
        "--expected-digest",
        json.loads(changed.stdout)["digest"],
    )
    assert repaired.returncode == 0, repaired.stderr
    assert run_helper("validate", "--session", str(session), "--area", "model").returncode == 0
    assert json.loads(repaired.stdout)["digest"] == digest
    accepted = run_helper(
        "accept", "--session", str(session), "--area", "model", "--digest", digest
    )
    assert accepted.returncode == 0, accepted.stderr
    cached = run_helper(
        "draft-cache",
        "--session",
        str(session),
        "--area",
        "model",
        "--id",
        str(uuid4()),
        "--revision",
        "1",
        "--status",
        "active",
    )
    assert cached.returncode == 0, cached.stderr
    prepared = run_helper("prepare-stage-request", "--session", str(session), "--area", "model")
    assert prepared.returncode == 0, prepared.stderr
    request = json.loads(Path(json.loads(prepared.stdout)["manifest"]).read_text())
    assert request["accepted_digest"] == digest
    assert {d["dataset"] for d in request["datasets"]} == set(canonical)
    for dataset in request["datasets"]:
        payload = Path(dataset["payload_file"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == dataset["sha256"]
        rows = json.loads(payload)
        # Natural-key sorting is transport normalization; record contents stay exact.
        assert sorted(json.dumps(row, sort_keys=True) for row in rows) == sorted(
            json.dumps(row, sort_keys=True) for row in canonical[dataset["dataset"]]
        )
