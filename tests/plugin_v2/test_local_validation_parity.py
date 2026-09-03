from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from gds_etl_workbench.domain.portable_validation import (
    METADATA_RECORD_VALIDATIONS,
    MODEL_RECORD_VALIDATIONS,
)
from gds_etl_workbench.tools.snapshots.metadata.archive import (
    build_snapshot_archive as build_metadata_snapshot_archive,
    encode_dataset,
)
from gds_etl_workbench.domain.snapshots.metadata import DATASETS as METADATA_DATASETS
from gds_etl_workbench.tools.snapshots.model.archive import build_model_snapshot_archive
from gds_etl_workbench.domain.snapshots.model import ModelSnapshot

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER = (
    REPOSITORY_ROOT
    / "plugins/v2/gds/skills/gds/scripts/gds-local.js"
)
COMMON_VALIDATION = (
    REPOSITORY_ROOT
    / "plugins/v2/gds/skills/gds/workbench/validation/common.js"
)


def run_helper(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(HELPER), *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def install(session: Path, area: str, archive: Path, snapshot_id: str) -> None:
    content = archive.read_bytes()
    result = run_helper(
        "snapshot-install",
        "--session",
        str(session),
        "--area",
        area,
        "--archive",
        str(archive),
        "--snapshot-id",
        snapshot_id,
        "--size-bytes",
        str(len(content)),
        "--sha256",
        hashlib.sha256(content).hexdigest(),
    )
    assert result.returncode == 0, result.stderr


def minimal_model_snapshot(source: dict[str, object]) -> ModelSnapshot:
    details = {
        "model_name": "SalesModel",
        "model_description": "Sales model.",
        "silver_model_naming_instructions": "Use PascalCase and an ID suffix.",
        "silver_model_audit_columns_template": None,
        "gold_model_naming_instructions": "Use PascalCase and a Key suffix.",
        "gold_model_technical_columns_template": None,
        "gold_model_audit_columns_template": None,
    }
    return ModelSnapshot.model_validate(
        {
            "model_id": 1,
            "model_name": "SalesModel",
            "model_revision": 2,
            "model_tenant_code": "TENANT_A",
            "other_active_model_names": [],
            "model_input_scope": {
                "details": details,
                "objects": [{
                    **source,
                    "model_input_scope_is_locked": False,
                    "is_active": True,
                }],
            },
            "profiling": {"profiles": []},
            "analysis": {"relationships": []},
            "assertion": {"documents": [], "records": []},
            "conceptual": {"objects": [], "relationships": []},
            "logical": {"submodels": [], "entities": [], "attributes": [], "relationships": []},
            "dimensional": {
                "submodels": [], "entities": [], "attributes": [], "relationships": [],
            },
            "model_binding": {"objects": [], "attributes": []},
            "mapping": {"dependencies": [], "objects": [], "attributes": []},
            "code_generation": {"artifacts": [], "source_systems": []},
            "validation": {"groups": [], "checks": []},
        },
        strict=False,
    )


def test_local_validator_supports_every_exported_backend_record_rule() -> None:
    result = subprocess.run(
        [
            "node",
            "-e",
            "process.stdout.write(JSON.stringify(require(process.argv[1]).supportedRecordRules))",
            str(COMMON_VALIDATION),
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    expected = {
        rule
        for rules in (*METADATA_RECORD_VALIDATIONS.values(), *MODEL_RECORD_VALIDATIONS.values())
        for rule in rules
    }

    assert set(json.loads(result.stdout)) == expected


def test_local_validation_accepts_server_generated_metadata_and_model_contracts(
    tmp_path: Path,
) -> None:
    source = {
        "tenant_code": "TENANT_A",
        "system_code": "CRM",
        "connection_code": "SOURCE",
        "object_schema": "sales",
        "object_name": "Customer",
    }
    metadata_rows: dict[str, list[dict[str, object]]] = {
        "project": [{
            "project_code": "PROJECT", "project_name": "Project",
            "project_description": None, "is_active": True,
        }],
        "tenant": [{
            "tenant_code": "TENANT_A", "project_code": "PROJECT",
            "tenant_name": "Tenant A", "tenant_description": None,
            "tenant_catalog": "tenant_a", "gds_admin_catalog": "admin",
            "gds_connection_tenant_code": None, "gds_connection_system_code": None,
            "gds_connection_code": None, "tenant_visibility": "private", "is_active": True,
        }],
        "system_type": [{
            "system_type_code": "DATABASE", "system_type_name": "Database",
            "system_type_description": None, "is_active": True,
        }],
        "system": [{
            "system_code": "CRM", "system_name": "CRM", "system_description": None,
            "system_type_code": "DATABASE", "is_active": True,
        }],
        "connection_type": [{
            "connection_type_code": "POSTGRES", "connection_type_name": "Postgres",
            "connection_type_description": None, "is_active": True,
        }],
        "connection": [{
            "tenant_code": "TENANT_A", "system_code": "CRM", "connection_code": "SOURCE",
            "connection_name": "Source", "connection_type_code": "POSTGRES",
            "has_foreign_catalog": True, "foreign_catalog": "source_catalog",
            "is_global_data_store": False, "is_active": True,
        }],
        "object_type": [{
            "object_type_code": "TABLE", "object_type_name": "Table",
            "object_type_description": None, "is_active": True,
        }],
        "zone": [{
            "zone_code": "source", "zone_name": "Source", "zone_description": None,
            "is_active": True,
        }],
        "source_object": [{
            **source, "source_tenant_code": "TENANT_A", "fc_object_schema": "sales",
            "fc_object_name": "Customer", "object_transformation": None,
            "object_description": None, "batch_attribute_name": None,
            "object_type_code": "TABLE", "zone_code": "source",
            "is_locked": False, "is_active": True,
        }],
    }
    encoded = tuple(
        encode_dataset(definition, metadata_rows.get(definition.name, []))
        for definition in METADATA_DATASETS
    )
    created = datetime(2026, 9, 3, tzinfo=UTC)
    metadata_id = uuid4()
    metadata_zip = tmp_path / "metadata.zip"
    build_metadata_snapshot_archive(
        metadata_zip,
        snapshot_id=metadata_id,
        tenant_code="TENANT_A",
        created_time=created,
        available_until=created + timedelta(hours=1),
        encoded_datasets=encoded,
        max_archive_bytes=16 * 1024 * 1024,
    )

    snapshot = minimal_model_snapshot(source)
    model_id = uuid4()
    model_zip = tmp_path / "model.zip"
    build_model_snapshot_archive(
        model_zip,
        snapshot_id=model_id,
        snapshot=snapshot,
        created_time=created,
        available_until=created + timedelta(hours=1),
        max_archive_bytes=16 * 1024 * 1024,
    )

    initialized = run_helper(
        "session-init", "--root", str(tmp_path), "--tenant", "TENANT_A"
    )
    assert initialized.returncode == 0, initialized.stderr
    session = Path(json.loads(initialized.stdout)["path"])
    install(session, "metadata", metadata_zip, str(metadata_id))
    install(session, "model", model_zip, str(model_id))
    added = run_helper(
        "task-add", "--session", str(session), "--area", "model",
        "--title", "Validate generated contracts", "--plan", '["Validate"]',
    )
    assert added.returncode == 0, added.stderr

    validated = run_helper("validate", "--session", str(session), "--area", "model")

    assert validated.returncode == 0, validated.stderr
    result = json.loads(validated.stdout)
    assert result["valid"] is True
    assert result["issues"] == []
