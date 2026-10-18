from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any


def write_snapshot_manifest(
    snapshot: Path,
    *,
    kind: str,
    snapshot_id: str,
    project_revision: int | None = None,
    tenant_code: str = "TENANT_A",
    project_id: int = 41,
    project_name: str = "Customer Project",
) -> None:
    catalog_path = snapshot / "catalog.json"
    catalog_document = json.loads(catalog_path.read_text())
    catalog_document["schema_version"] = "3.0"
    if kind == "project":
        catalog_document["project"] = {
            "project_id": project_id,
            "project_name": project_name,
            "project_revision": project_revision,
            "tenant_code": tenant_code,
        }
    catalog_path.write_text(json.dumps(catalog_document))
    members: list[dict[str, object]] = []
    for file in sorted(path for path in snapshot.rglob("*") if path.is_file()):
        if file.name == "manifest.json" and file.parent == snapshot:
            continue
        content = file.read_bytes()
        members.append(
            {
                "path": file.relative_to(snapshot).as_posix(),
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    catalog = next(member for member in members if member["path"] == "catalog.json")
    manifest: dict[str, object] = {
        "schema_version": "3.0",
        "snapshot_kind": kind,
        "snapshot_id": snapshot_id,
        "catalog": {"path": "catalog.json", "sha256": catalog["sha256"]},
        "members": members,
    }
    if project_revision is not None:
        manifest["project_revision"] = project_revision
    if kind == "project":
        manifest.update(project_id=project_id, project_name=project_name)
    else:
        manifest["tenant_code"] = tenant_code
    (snapshot / "manifest.json").write_text(json.dumps(manifest))


def archive_snapshot(snapshot: Path, archive: Path) -> bytes:
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for file in sorted(path for path in snapshot.rglob("*") if path.is_file()):
            output.write(file, (Path(snapshot.name) / file.relative_to(snapshot)).as_posix())
    return archive.read_bytes()


def write_metadata_snapshot(session: Path) -> None:
    snapshot = session / "metadata" / "metadata-snapshot"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "metadata",
                "sections": [
                    {
                        "name": "operational",
                        "datasets": [
                            {
                                "name": "source_object",
                                "record_type": "source_object",
                                "row_count": 2,
                                "canonical_key": [
                                    "tenant_code",
                                    "system_code",
                                    "connection_code",
                                    "object_schema",
                                    "object_name",
                                ],
                                "rows_file": "data/source_object.jsonl",
                                "schema_file": "schemas/source_object.schema.json",
                            },
                            {
                                "name": "source_attribute",
                                "record_type": "source_attribute",
                                "row_count": 0,
                                "canonical_key": [
                                    "tenant_code",
                                    "system_code",
                                    "connection_code",
                                    "object_schema",
                                    "object_name",
                                    "attribute_name",
                                ],
                                "rows_file": "data/source_attribute.jsonl",
                                "schema_file": "schemas/source_attribute.schema.json",
                            },
                        ],
                    }
                ],
            }
        )
    )
    records = [
        {
            "tenant_code": "TENANT_A",
            "system_code": "CRM",
            "connection_code": "MAIN",
            "object_schema": "sales",
            "object_name": "Customer",
            "is_active": True,
        },
        {
            "tenant_code": "TENANT_A",
            "system_code": "ERP",
            "connection_code": "MAIN",
            "object_schema": "sales",
            "object_name": "Order",
            "is_active": True,
        },
    ]
    (snapshot / "data" / "source_object.jsonl").write_text(
        "".join(f"{json.dumps(record)}\n" for record in records)
    )
    (snapshot / "data" / "source_attribute.jsonl").write_text("")
    fields = {
        name: {"type": field_type}
        for name, field_type in (
            ("tenant_code", "string"),
            ("system_code", "string"),
            ("connection_code", "string"),
            ("object_schema", "string"),
            ("object_name", "string"),
            ("is_active", "boolean"),
        )
    }
    (snapshot / "schemas" / "source_object.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": fields,
                "required": list(fields),
                "x-gds-change-set-eligible": True,
                "x-gds-canonical-key": [
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                ],
                "x-gds-references": [],
            }
        )
    )
    attribute_fields = {
        **fields,
        "attribute_name": {"type": "string"},
    }
    (snapshot / "schemas" / "source_attribute.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": attribute_fields,
                "required": list(attribute_fields),
                "x-gds-change-set-eligible": True,
                "x-gds-canonical-key": [
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                    "attribute_name",
                ],
                "x-gds-references": [
                    {
                        "columns": [
                            "tenant_code",
                            "system_code",
                            "connection_code",
                            "object_schema",
                            "object_name",
                        ],
                        "target_record_type": "source_object",
                        "target_columns": [
                            "tenant_code",
                            "system_code",
                            "connection_code",
                            "object_schema",
                            "object_name",
                        ],
                        "nullable": False,
                    }
                ],
            }
        )
    )
    write_snapshot_manifest(
        snapshot,
        kind="metadata",
        snapshot_id="snapshot-01",
    )


def write_project_snapshot(session: Path) -> None:
    snapshot = session / "project" / "project-snapshot"
    (snapshot / "data").mkdir(parents=True)
    (snapshot / "schemas").mkdir()
    datasets: list[dict[str, Any]] = [
        {
            "name": "project_details",
            "row_count": 1,
            "canonical_key": [],
            "rows_file": "data/project_details.jsonl",
            "schema_file": "schemas/project_details.schema.json",
        },
        {
            "name": "logical_entity",
            "row_count": 0,
            "canonical_key": ["logical_entity_schema_name", "logical_entity_name"],
            "rows_file": "data/logical_entity.jsonl",
            "schema_file": "schemas/logical_entity.schema.json",
        },
        {
            "name": "logical_attribute",
            "row_count": 0,
            "canonical_key": [
                "logical_entity_schema_name",
                "logical_entity_name",
                "logical_attribute_name",
            ],
            "rows_file": "data/logical_attribute.jsonl",
            "schema_file": "schemas/logical_attribute.schema.json",
        },
    ]
    (snapshot / "catalog.json").write_text(
        json.dumps(
            {
                "snapshot_kind": "project",
                "sections": [{"name": "logical", "datasets": datasets}],
            }
        )
    )
    for dataset in datasets:
        rows = (
            '{"project_purpose":"Current purpose"}\n'
            if dataset["name"] == "project_details"
            else ""
        )
        (snapshot / dataset["rows_file"]).write_text(rows)
    (snapshot / "schemas" / "project_details.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"project_purpose": {"type": "string"}},
                "required": ["project_purpose"],
                "x-gds-change-set-eligible": True,
            }
        )
    )
    (snapshot / "schemas" / "logical_entity.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "logical_entity_schema_name": {"type": "string"},
                    "logical_entity_name": {"type": "string"},
                },
                "required": ["logical_entity_schema_name", "logical_entity_name"],
                "x-gds-change-set-eligible": True,
            }
        )
    )
    (snapshot / "schemas" / "logical_attribute.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "logical_entity_schema_name": {"type": "string"},
                    "logical_entity_name": {"type": "string"},
                    "logical_attribute_name": {"type": "string"},
                    "logical_attribute_is_nullable": {"type": "boolean"},
                    "logical_attribute_is_natural_key": {"type": "boolean"},
                    "logical_attribute_is_surrogate_key": {"type": "boolean"},
                    "sources": {"type": "array", "items": {"type": "object"}},
                },
                "required": [
                    "logical_entity_schema_name",
                    "logical_entity_name",
                    "logical_attribute_name",
                    "logical_attribute_is_nullable",
                    "logical_attribute_is_natural_key",
                    "logical_attribute_is_surrogate_key",
                    "sources",
                ],
                "x-gds-change-set-eligible": True,
            }
        )
    )
    write_snapshot_manifest(
        snapshot,
        kind="project",
        snapshot_id="project-snapshot-01",
        project_revision=8,
    )
