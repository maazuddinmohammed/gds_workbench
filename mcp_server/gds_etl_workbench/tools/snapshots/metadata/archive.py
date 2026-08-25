"""Deterministic ID-free JSONL and Metadata Snapshot ZIP generation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from pydantic import ValidationError

from gds_etl_workbench.tools.snapshots.archive import (
    SnapshotArchive,
    SnapshotContractError,
    SnapshotMember,
    SnapshotPayloadTooLargeError,
    write_snapshot_archive,
)
from gds_etl_workbench.tools.snapshots.archive import (
    json_document as _json_document,
)
from gds_etl_workbench.tools.snapshots.archive import (
    json_line as _json_line,
)
from gds_etl_workbench.tools.snapshots.archive import (
    utc_timestamp as _utc_timestamp,
)
from gds_etl_workbench.tools.snapshots.dataset_description import DatasetDescription

from .contracts import (
    DATASETS,
    PHYSICAL_TABLE_COUNT,
    DatasetDefinition,
    SnapshotSection,
    natural_key_normalization_document,
    normalize_natural_key_value,
)
from .guidance import build_metadata_dataset_description

__all__ = [
    "EncodedDataset",
    "RootDocuments",
    "SnapshotArchive",
    "SnapshotContractError",
    "SnapshotPayloadTooLargeError",
    "MetadataDatasetDocument",
    "build_dataset_document",
    "build_root_documents",
    "build_snapshot_archive",
    "encode_dataset",
]


@dataclass(frozen=True, slots=True)
class EncodedDataset:
    definition: DatasetDefinition
    rows_jsonl: bytes
    lookup_jsonl: bytes | None
    row_count: int


@dataclass(frozen=True, slots=True)
class RootDocuments:
    catalog_json: bytes
    schemas: tuple[tuple[str, bytes], ...]


@dataclass(frozen=True, slots=True)
class MetadataDatasetDocument:
    schema: dict[str, object]
    description: DatasetDescription


def build_dataset_document(definition: DatasetDefinition) -> MetadataDatasetDocument:
    """Build one standard JSON Schema plus GDS key/reference metadata."""
    generated = definition.row_model.model_json_schema(mode="serialization")
    properties = generated.get("properties")
    if not isinstance(properties, dict):
        raise SnapshotContractError(f"{definition.name} generated an invalid JSON Schema")
    typed_properties = cast(dict[str, object], properties)
    for field_name, expected_value in definition.fixed_values:
        raw_property = typed_properties.get(field_name)
        if not isinstance(raw_property, dict):
            raise SnapshotContractError(
                f"{definition.name}.{field_name} fixed field is absent from its schema"
            )
        cast(dict[str, object], raw_property)["const"] = expected_value

    raw_required = generated.get("required", [])
    if not isinstance(raw_required, list):
        raise SnapshotContractError(f"{definition.name} generated invalid required-field metadata")
    required_items = cast(list[object], raw_required)
    if not all(isinstance(field, str) for field in required_items):
        raise SnapshotContractError(f"{definition.name} generated invalid required-field metadata")
    required = cast(list[str], required_items)
    required_fields = set(required)
    description = build_metadata_dataset_description(
        definition,
        typed_properties,
        required_fields,
    )
    description_document = description.model_dump(mode="json")

    schema: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": definition.schema_path,
        "title": definition.label,
        "description": (
            f"One flat, ID-free {definition.record_type} record. "
            "Named key strings compare using x-gds-key-normalization."
        ),
        "type": "object",
        "additionalProperties": False,
        "properties": typed_properties,
        "required": required,
        "x-gds-dataset": definition.name,
        "x-gds-record-type": definition.record_type,
        "x-gds-change-set-eligible": definition.change_set_eligible,
        "x-gds-canonical-key": list(definition.canonical_key),
        "x-gds-key-normalization": natural_key_normalization_document(),
        "x-gds-unique-constraints": [
            list(constraint) for constraint in definition.unique_constraints
        ],
        "x-gds-references": [
            {
                "columns": list(reference.columns),
                "target_record_type": reference.target_record_type,
                "target_columns": list(reference.target_columns),
                "nullable": reference.nullable,
            }
            for reference in definition.references
        ],
        "x-gds-fixed-values": dict(definition.fixed_values),
        "x-gds-population-rules": description_document["population_rules"],
        "x-gds-columns": description_document["columns"],
    }
    return MetadataDatasetDocument(schema=schema, description=description)


def encode_dataset(
    definition: DatasetDefinition,
    rows: Sequence[Mapping[str, object]],
) -> EncodedDataset:
    """Validate, sort, and encode one flat ID-free dataset."""
    encoded_rows: list[dict[str, object]] = []
    for row_number, row in enumerate(rows, start=1):
        try:
            record = definition.row_model.model_validate(row)
        except ValidationError as exc:
            raise SnapshotContractError(
                f"{definition.name} row {row_number} does not match its fixed schema"
            ) from exc
        encoded_row = record.model_dump(mode="json")
        if any(encoded_row.get(field) != value for field, value in definition.fixed_values):
            raise SnapshotContractError(
                f"{definition.name} row {row_number} violates its fixed dataset values"
            )
        encoded_rows.append(encoded_row)

    encoded_rows.sort(key=lambda row: _key_sort_value(definition.canonical_key, row))
    for unique_constraint in definition.unique_constraints:
        seen: set[tuple[object, ...]] = set()
        for row in encoded_rows:
            key = _normalized_key(unique_constraint, row)
            if key in seen:
                raise SnapshotContractError(
                    f"{definition.name} contains a duplicate unique key: "
                    f"{', '.join(unique_constraint)}"
                )
            seen.add(key)

    row_lines = [_json_line(row) for row in encoded_rows]
    lookup_jsonl: bytes | None = None
    if definition.lookup_path is not None:
        lookup_lines = [
            _json_line(
                {
                    **{field: row[field] for field in definition.search_fields},
                    "line": line_number,
                }
            )
            for line_number, row in enumerate(encoded_rows, start=1)
        ]
        lookup_jsonl = "".join(lookup_lines).encode("utf-8")

    return EncodedDataset(
        definition=definition,
        rows_jsonl="".join(row_lines).encode("utf-8"),
        lookup_jsonl=lookup_jsonl,
        row_count=len(encoded_rows),
    )


def build_root_documents(encoded_datasets: Sequence[EncodedDataset]) -> RootDocuments:
    """Build the small agent catalog and one schema per dataset."""
    encoded_by_name = _complete_encoded_registry(encoded_datasets)
    for encoded in encoded_by_name.values():
        _validate_encoded_dataset(encoded)
    _validate_snapshot_references(encoded_by_name)
    sections: list[dict[str, object]] = []
    for section, label in (
        (SnapshotSection.FOUNDATIONAL, "Foundational"),
        (SnapshotSection.REFERENCE, "Reference"),
        (SnapshotSection.OPERATIONAL, "Operational"),
    ):
        sections.append(
            {
                "name": section.value,
                "label": label,
                "datasets": [
                    {
                        "name": definition.name,
                        "label": definition.label,
                        "record_type": definition.record_type,
                        "row_count": encoded_by_name[definition.name].row_count,
                        "canonical_key": list(definition.canonical_key),
                        "search_fields": list(definition.search_fields),
                        "schema_file": definition.schema_path,
                        "search_file": definition.search_path,
                        "rows_file": definition.rows_path,
                        "search_result_complete": definition.lookup_path is None,
                    }
                    for definition in DATASETS
                    if definition.section is section
                ],
            }
        )

    catalog = {
        "schema_version": "2.0",
        "snapshot_kind": "metadata",
        "row_format": "flat-json-lines",
        "database_ids_included": False,
        "instructions": [
            "Read catalog.json first; do not recursively load this archive into context.",
            "Choose only the needed dataset or record group.",
            "Search search_file using canonical_key or search_fields.",
            "When search_result_complete is false, use line to read that line from rows_file.",
            "Read schema_file only when field, key, or reference meaning is needed.",
        ],
        "record_groups": [
            {
                "name": "objects",
                "datasets": [
                    "source_object",
                    "bronze_object",
                    "silver_object",
                    "gold_object",
                ],
            },
            {
                "name": "attributes",
                "datasets": [
                    "source_attribute",
                    "bronze_attribute",
                    "silver_attribute",
                    "gold_attribute",
                ],
            },
        ],
        "sections": sections,
    }
    schemas = tuple(
        (
            definition.schema_path,
            _json_document(build_dataset_document(definition).schema),
        )
        for definition in DATASETS
    )
    return RootDocuments(catalog_json=_json_document(catalog), schemas=schemas)


def build_snapshot_archive(
    output: Path,
    *,
    snapshot_id: UUID,
    tenant_code: str,
    created_time: datetime,
    available_until: datetime,
    encoded_datasets: Sequence[EncodedDataset],
    max_archive_bytes: int,
) -> SnapshotArchive:
    """Create and verify one deterministic Metadata Snapshot ZIP."""
    normalized_tenant_code = tenant_code.strip()
    if not normalized_tenant_code or len(normalized_tenant_code) > 100:
        raise SnapshotContractError("tenant_code is invalid")
    if snapshot_id.version != 4:
        raise SnapshotContractError("snapshot_id must be a UUID version 4")
    created_at = _utc_timestamp("created_time", created_time)
    available_at = _utc_timestamp("available_until", available_until)
    if available_until <= created_time:
        raise SnapshotContractError("available_until must be after created_time")
    roots = build_root_documents(encoded_datasets)
    encoded_by_name = {encoded.definition.name: encoded for encoded in encoded_datasets}
    members = [SnapshotMember("catalog.json", roots.catalog_json)]
    members.extend(SnapshotMember(path, content) for path, content in roots.schemas)
    for definition in DATASETS:
        encoded = encoded_by_name[definition.name]
        _validate_encoded_dataset(encoded)
        members.append(SnapshotMember(definition.rows_path, encoded.rows_jsonl, encoded.row_count))
        if definition.lookup_path is not None:
            if encoded.lookup_jsonl is None:
                raise SnapshotContractError(f"{definition.name} lookup file is missing")
            members.append(
                SnapshotMember(
                    definition.lookup_path,
                    encoded.lookup_jsonl,
                    encoded.row_count,
                )
            )

    row_count = sum(encoded.row_count for encoded in encoded_datasets)
    section_counts = {
        section.value: {
            "dataset_count": sum(definition.section is section for definition in DATASETS),
            "row_count": sum(
                encoded_by_name[definition.name].row_count
                for definition in DATASETS
                if definition.section is section
            ),
        }
        for section in SnapshotSection
    }

    def build_manifest(
        member_records: tuple[dict[str, object], ...],
        expanded_bytes: int,
    ) -> Mapping[str, object]:
        return {
            "schema_version": "2.0",
            "snapshot_kind": "metadata",
            "snapshot_id": str(snapshot_id),
            "tenant_code": normalized_tenant_code,
            "database_ids_included": False,
            "generated_at": created_at,
            "available_until": available_at,
            "counts": {
                "physical_table_count": PHYSICAL_TABLE_COUNT,
                "logical_dataset_count": len(DATASETS),
                "lookup_file_count": sum(
                    definition.lookup_path is not None for definition in DATASETS
                ),
                "row_count": row_count,
                "file_count": len(members) + 1,
                "expanded_bytes": expanded_bytes,
            },
            "sections": section_counts,
            "catalog": {
                "path": "catalog.json",
                "sha256": hashlib.sha256(roots.catalog_json).hexdigest(),
            },
            "schemas": {
                "directory": "schemas",
                "dataset_count": len(DATASETS),
            },
            "members": member_records,
        }

    return write_snapshot_archive(
        output,
        archive_root="metadata-snapshot",
        members=members,
        row_count=row_count,
        max_archive_bytes=max_archive_bytes,
        build_manifest=build_manifest,
    )


def _complete_encoded_registry(
    encoded_datasets: Sequence[EncodedDataset],
) -> dict[str, EncodedDataset]:
    encoded_by_name: dict[str, EncodedDataset] = {}
    for encoded in encoded_datasets:
        name = encoded.definition.name
        if name in encoded_by_name:
            raise SnapshotContractError(f"duplicate encoded dataset: {name}")
        encoded_by_name[name] = encoded
    expected_names = {definition.name for definition in DATASETS}
    if set(encoded_by_name) != expected_names:
        raise SnapshotContractError("encoded datasets do not match the fixed snapshot registry")
    for definition in DATASETS:
        if encoded_by_name[definition.name].definition != definition:
            raise SnapshotContractError(
                f"encoded dataset definition does not match the registry: {definition.name}"
            )
    return encoded_by_name


def _validate_encoded_dataset(encoded: EncodedDataset) -> None:
    try:
        row_lines = encoded.rows_jsonl.decode("utf-8").splitlines()
        lookup_lines = (
            encoded.lookup_jsonl.decode("utf-8").splitlines()
            if encoded.lookup_jsonl is not None
            else None
        )
    except UnicodeDecodeError as exc:
        raise SnapshotContractError(f"{encoded.definition.name} JSONL is not valid UTF-8") from exc
    if encoded.rows_jsonl and not encoded.rows_jsonl.endswith(b"\n"):
        raise SnapshotContractError(f"{encoded.definition.name} rows JSONL lacks final newline")
    if encoded.row_count != len(row_lines):
        raise SnapshotContractError(f"{encoded.definition.name} JSONL row count is inconsistent")
    if encoded.definition.lookup_path is None:
        if lookup_lines is not None:
            raise SnapshotContractError(f"{encoded.definition.name} has an unexpected lookup file")
    else:
        if lookup_lines is None or len(lookup_lines) != encoded.row_count:
            raise SnapshotContractError(
                f"{encoded.definition.name} lookup row count is inconsistent"
            )
        if encoded.lookup_jsonl and not encoded.lookup_jsonl.endswith(b"\n"):
            raise SnapshotContractError(
                f"{encoded.definition.name} lookup JSONL lacks final newline"
            )

    expected_columns = list(encoded.definition.row_model.model_fields)
    for line_number, row_line in enumerate(row_lines, start=1):
        try:
            parsed_row: object = json.loads(row_line)
        except json.JSONDecodeError as exc:
            raise SnapshotContractError(
                f"{encoded.definition.name} contains invalid rows JSONL"
            ) from exc
        if not isinstance(parsed_row, dict):
            raise SnapshotContractError(
                f"{encoded.definition.name} rows JSONL violates its object contract"
            )
        row = cast(dict[str, object], parsed_row)
        if list(row) != expected_columns:
            raise SnapshotContractError(
                f"{encoded.definition.name} rows JSONL violates column order"
            )
        try:
            encoded.definition.row_model.model_validate_json(row_line)
        except ValidationError as exc:
            raise SnapshotContractError(
                f"{encoded.definition.name} rows JSONL violates its schema"
            ) from exc
        if any(row.get(field) != value for field, value in encoded.definition.fixed_values):
            raise SnapshotContractError(
                f"{encoded.definition.name} rows JSONL violates fixed dataset values"
            )
        if lookup_lines is not None:
            try:
                parsed_lookup: object = json.loads(lookup_lines[line_number - 1])
            except json.JSONDecodeError as exc:
                raise SnapshotContractError(
                    f"{encoded.definition.name} contains invalid lookup JSONL"
                ) from exc
            expected_lookup = {
                **{field: row[field] for field in encoded.definition.search_fields},
                "line": line_number,
            }
            if parsed_lookup != expected_lookup:
                raise SnapshotContractError(
                    f"{encoded.definition.name} lookup does not match rows JSONL"
                )


def _validate_snapshot_references(
    encoded_by_name: Mapping[str, EncodedDataset],
) -> None:
    rows_by_name = {
        definition.name: _parse_rows(encoded_by_name[definition.name]) for definition in DATASETS
    }
    keys_by_record_type: dict[str, set[tuple[object, ...]]] = {}
    for definition in DATASETS:
        record_keys = keys_by_record_type.setdefault(definition.record_type, set())
        for row in rows_by_name[definition.name]:
            key = _normalized_key(definition.canonical_key, row)
            if key in record_keys:
                raise SnapshotContractError(
                    f"{definition.record_type} contains a duplicate cross-dataset key"
                )
            record_keys.add(key)

    for definition in DATASETS:
        for row in rows_by_name[definition.name]:
            for reference in definition.references:
                local_values = tuple(row[column] for column in reference.columns)
                if reference.nullable and any(value is None for value in local_values):
                    continue
                if any(value is None for value in local_values):
                    raise SnapshotContractError(
                        f"{definition.name} contains an incomplete natural-key reference"
                    )
                target_key = tuple(
                    _normalize_key_value(target_column, value)
                    for target_column, value in zip(
                        reference.target_columns,
                        local_values,
                        strict=True,
                    )
                )
                if target_key not in keys_by_record_type.get(
                    reference.target_record_type,
                    set(),
                ):
                    raise SnapshotContractError(
                        f"{definition.name} contains an unresolved natural-key reference"
                    )


def _parse_rows(encoded: EncodedDataset) -> list[dict[str, object]]:
    return [
        cast(dict[str, object], json.loads(line))
        for line in encoded.rows_jsonl.decode("utf-8").splitlines()
    ]


def _normalized_key(
    columns: tuple[str, ...],
    row: Mapping[str, object],
) -> tuple[object, ...]:
    return tuple(_normalize_key_value(column, row[column]) for column in columns)


def _normalize_key_value(column: str, value: object) -> object:
    return normalize_natural_key_value(column, value)


def _key_sort_value(
    columns: tuple[str, ...],
    row: Mapping[str, object],
) -> tuple[tuple[int, str], ...]:
    key: list[tuple[int, str]] = []
    for value in _normalized_key(columns, row):
        if value is None:
            key.append((0, ""))
        elif isinstance(value, bool):
            key.append((1, "1" if value else "0"))
        elif isinstance(value, int):
            key.append((2, f"{value:+020d}"))
        elif isinstance(value, (date, datetime)):
            key.append((3, value.isoformat()))
        else:
            key.append((4, str(value)))
    return tuple(key)
