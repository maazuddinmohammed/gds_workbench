"""Deterministic ID-free Model Snapshot catalog, JSONL, and ZIP generation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from gds_etl_workbench.domain.modeling_records import (
    ModelingRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.tools.snapshots.archive import (
    SnapshotArchive,
    SnapshotContractError,
    SnapshotMember,
    json_document,
    json_line,
    utc_timestamp,
    write_snapshot_archive,
)

from .contracts import (
    DATASETS,
    MODEL_SECTIONS,
    ModelingDatasetDefinition,
    ModelSnapshot,
    build_model_dataset_schema,
    model_snapshot_records,
)

_SECTION_DESCRIPTIONS = {
    "model_input_scope": "Model header and selected Source or Bronze input Objects.",
    "profiling": "Applied Attribute profiles.",
    "analysis": "Applied relationship analysis evidence.",
    "assertion": "Applied source assertion documents and records.",
    "conceptual": "Applied conceptual Objects and Relationships.",
    "logical": "Applied logical Submodels, Entities, Attributes, and Relationships.",
    "dimensional": "Applied dimensional Submodels, Entities, Attributes, and Relationships.",
    "model_binding": "Applied Entity-to-Object and Attribute-to-Attribute Bindings.",
    "mapping": "Applied source-to-target Mapping and dependency records.",
    "code_generation": (
        "Applied complete Code Artifacts and their contributing source Systems; Apply "
        "never executes or deploys them."
    ),
    "validation": "Applied Validation Groups and Checks; execution results stay local.",
}

_SECTION_AUTHORING_PREREQUISITES: dict[str, dict[str, object]] = {
    "code_generation": {
        "required_applied_sections": ["mapping"],
        "optional_applied_sections": [],
        "successive_change_set_required": False,
    },
    "validation": {
        "required_applied_sections": ["mapping"],
        "optional_applied_sections": ["code_generation"],
        "successive_change_set_required": False,
    },
}


@dataclass(frozen=True, slots=True)
class EncodedModelDataset:
    definition: ModelingDatasetDefinition
    rows_jsonl: bytes
    row_count: int


def encode_model_snapshot(snapshot: ModelSnapshot) -> tuple[EncodedModelDataset, ...]:
    """Validate, sort, and encode every Model Snapshot dataset."""
    records_by_dataset = model_snapshot_records(snapshot)
    return tuple(
        _encode_dataset(definition, records_by_dataset[definition.name]) for definition in DATASETS
    )


def build_model_snapshot_archive(
    output: Path,
    *,
    snapshot_id: UUID,
    snapshot: ModelSnapshot,
    created_time: datetime,
    available_until: datetime,
    max_archive_bytes: int,
) -> SnapshotArchive:
    """Create and verify one deterministic Model Snapshot ZIP."""
    if snapshot_id.version != 4:
        raise SnapshotContractError("snapshot_id must be a UUID version 4")
    generated_at = utc_timestamp("created_time", created_time)
    available_at = utc_timestamp("available_until", available_until)
    if available_until <= created_time:
        raise SnapshotContractError("available_until must be after created_time")

    encoded_datasets = encode_model_snapshot(snapshot)
    encoded_by_name = {encoded.definition.name: encoded for encoded in encoded_datasets}
    catalog = {
        "schema_version": "2.0",
        "snapshot_kind": "model",
        "row_format": "nested-json-lines",
        "database_ids_included": False,
        "model": {
            "model_id": snapshot.model_id,
            "model_name": snapshot.model_name,
            "model_revision": snapshot.model_revision,
            "tenant_code": snapshot.model_tenant_code,
            "other_active_model_names": list(snapshot.other_active_model_names),
        },
        "instructions": [
            "Read catalog.json first; do not recursively load this archive into context.",
            "Choose only the needed Model section and dataset.",
            "Search rows_file using the published canonical_key.",
            "Read schema_file before authoring Model Change Set records.",
            "Follow each schema's x-gds authoring extensions and section prerequisites.",
        ],
        "sections": [
            {
                "name": section,
                "description": _SECTION_DESCRIPTIONS[section],
                "authoring_prerequisites": _SECTION_AUTHORING_PREREQUISITES.get(
                    section,
                    {
                        "required_applied_sections": [],
                        "optional_applied_sections": [],
                        "successive_change_set_required": False,
                    },
                ),
                "datasets": [
                    {
                        "name": definition.name,
                        "row_count": encoded_by_name[definition.name].row_count,
                        "canonical_key": list(definition.canonical_key),
                        "change_set_eligible": definition.change_set_eligible,
                        "schema_file": definition.schema_path,
                        "rows_file": definition.rows_path,
                    }
                    for definition in DATASETS
                    if definition.section == section
                ],
            }
            for section in MODEL_SECTIONS
        ],
    }
    catalog_json = json_document(catalog)
    members = [SnapshotMember("catalog.json", catalog_json)]
    members.extend(
        SnapshotMember(
            definition.schema_path,
            json_document(build_model_dataset_schema(definition)),
        )
        for definition in DATASETS
    )
    members.extend(
        SnapshotMember(
            encoded.definition.rows_path,
            encoded.rows_jsonl,
            encoded.row_count,
        )
        for encoded in encoded_datasets
    )
    row_count = sum(encoded.row_count for encoded in encoded_datasets)
    section_counts = {
        section: {
            "dataset_count": sum(definition.section == section for definition in DATASETS),
            "row_count": sum(
                encoded_by_name[definition.name].row_count
                for definition in DATASETS
                if definition.section == section
            ),
        }
        for section in MODEL_SECTIONS
    }

    def build_manifest(
        member_records: tuple[dict[str, object], ...],
        expanded_bytes: int,
    ) -> Mapping[str, object]:
        return {
            "schema_version": "2.0",
            "snapshot_kind": "model",
            "snapshot_id": str(snapshot_id),
            "model_id": snapshot.model_id,
            "model_name": snapshot.model_name,
            "model_revision": snapshot.model_revision,
            "database_ids_included": False,
            "generated_at": generated_at,
            "available_until": available_at,
            "counts": {
                "logical_dataset_count": len(DATASETS),
                "row_count": row_count,
                "file_count": len(members) + 1,
                "expanded_bytes": expanded_bytes,
            },
            "sections": section_counts,
            "catalog": {
                "path": "catalog.json",
                "sha256": hashlib.sha256(catalog_json).hexdigest(),
            },
            "schemas": {"directory": "schemas/model", "dataset_count": len(DATASETS)},
            "members": member_records,
        }

    return write_snapshot_archive(
        output,
        archive_root="model-snapshot",
        members=members,
        row_count=row_count,
        max_archive_bytes=max_archive_bytes,
        build_manifest=build_manifest,
    )


def _encode_dataset(
    definition: ModelingDatasetDefinition,
    records: Sequence[ModelingRecord],
) -> EncodedModelDataset:
    validated = [
        definition.row_model.model_validate(record.model_dump(mode="python"), strict=True)
        for record in records
    ]
    validated.sort(
        key=lambda record: tuple(
            str(normalize_model_key_value(getattr(record, field)))
            for field in definition.canonical_key
        )
    )
    seen: set[tuple[object, ...]] = set()
    lines: list[str] = []
    for record in validated:
        key = tuple(
            normalize_model_key_value(getattr(record, field)) for field in definition.canonical_key
        )
        if key in seen:
            raise SnapshotContractError(f"{definition.name} contains a duplicate canonical key")
        seen.add(key)
        lines.append(json_line(record.model_dump(mode="json")))
    return EncodedModelDataset(
        definition=definition,
        rows_jsonl="".join(lines).encode("utf-8"),
        row_count=len(lines),
    )
