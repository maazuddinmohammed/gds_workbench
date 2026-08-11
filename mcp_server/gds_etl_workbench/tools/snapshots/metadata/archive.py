"""Deterministic JSONL, root documents, and ZIP generation."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID

from .contracts import (
    DATASETS,
    TABLES,
    TABLES_BY_NAME,
    ColumnDefinition,
    DatasetDefinition,
    SnapshotSection,
    TableDefinition,
)


def build_schema_document() -> dict[str, object]:
    """Build the small viewer contract without database rows or checksums."""
    datasets: list[dict[str, object]] = []
    for dataset in DATASETS:
        table = TABLES_BY_NAME[dataset.database_table]
        datasets.append(
            {
                "name": dataset.name,
                "label": dataset.label,
                "database_table": dataset.database_table,
                "section": dataset.section.value,
                "change_set_eligible": dataset.change_set_eligible,
                "data_files": [dataset.data_path],
                "primary_key": list(dataset.primary_key),
                "display_columns": list(dataset.display_columns),
                "unique_column_groups": [
                    list(column_group) for column_group in table.unique_column_groups
                ],
                "columns": [
                    {
                        "name": column.name,
                        "type": column.type,
                        "nullable": column.nullable,
                        "generated": column.generated,
                    }
                    for column in table.columns
                ],
                "foreign_keys": [
                    {
                        "columns": list(foreign_key.columns),
                        "references_table": foreign_key.references_table,
                        "references_columns": list(foreign_key.references_columns),
                    }
                    for foreign_key in table.foreign_keys
                ],
            }
        )
    return {
        "schema_version": "1.0",
        "snapshot_kind": "metadata",
        "datasets": datasets,
    }


class SnapshotContractError(ValueError):
    """A safe failure caused by invalid snapshot input or schema drift."""


class SnapshotPayloadTooLargeError(SnapshotContractError):
    """The validated expanded or compressed snapshot exceeds its fixed limit."""


@dataclass(frozen=True, slots=True)
class EncodedDataset:
    definition: DatasetDefinition
    rows_jsonl: bytes
    index_jsonl: bytes
    row_count: int


@dataclass(frozen=True, slots=True)
class RootDocuments:
    schema_json: bytes
    index_json: bytes


@dataclass(frozen=True, slots=True)
class SnapshotArchive:
    path: Path
    size_bytes: int
    expanded_bytes: int
    row_count: int
    sha256: str


def encode_dataset(
    definition: DatasetDefinition,
    rows: Sequence[Mapping[str, object]],
) -> EncodedDataset:
    """Validate, order, and encode one dataset without filesystem access."""
    table = TABLES_BY_NAME[definition.database_table]
    expected_columns = tuple(column.name for column in table.columns)
    expected_column_set = frozenset(expected_columns)
    columns_by_name = {column.name: column for column in table.columns}
    encoded_rows: list[dict[str, object]] = []
    for row in rows:
        if frozenset(row) != expected_column_set:
            raise SnapshotContractError(
                f"{definition.name} row does not match its fixed column contract"
            )
        encoded_row: dict[str, object] = {}
        for column_name in expected_columns:
            column = columns_by_name[column_name]
            encoded_row[column_name] = _encode_column_value(
                definition.name,
                column,
                row[column_name],
            )
        encoded_rows.append(encoded_row)

    encoded_rows.sort(key=lambda row: _primary_key_sort_key(definition, table, row))
    seen_primary_keys: set[tuple[object, ...]] = set()
    row_lines: list[str] = []
    index_lines: list[str] = []
    for line_number, row in enumerate(encoded_rows, start=1):
        primary_key = {column_name: row[column_name] for column_name in definition.primary_key}
        primary_key_tuple = tuple(primary_key.values())
        if primary_key_tuple in seen_primary_keys:
            raise SnapshotContractError(f"{definition.name} contains a duplicate primary key")
        seen_primary_keys.add(primary_key_tuple)
        row_lines.append(_json_line(row))
        index_lines.append(
            _json_line(
                {
                    "primary_key": primary_key,
                    "label": _index_label(definition, row),
                    "file": "rows.jsonl",
                    "line": line_number,
                }
            )
        )

    return EncodedDataset(
        definition=definition,
        rows_jsonl="".join(row_lines).encode("utf-8"),
        index_jsonl="".join(index_lines).encode("utf-8"),
        row_count=len(encoded_rows),
    )


def build_root_documents(encoded_datasets: Sequence[EncodedDataset]) -> RootDocuments:
    """Build deterministic viewer and navigation documents for one complete snapshot."""
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

    sections: list[dict[str, object]] = []
    for section, label in (
        (SnapshotSection.FOUNDATION, "Foundation"),
        (SnapshotSection.METADATA, "Metadata"),
    ):
        sections.append(
            {
                "name": section.value,
                "label": label,
                "datasets": [
                    {
                        "name": definition.name,
                        "label": definition.label,
                        "row_count": encoded_by_name[definition.name].row_count,
                        "data_path": definition.data_path,
                        "table_index_path": definition.index_path,
                        "primary_key": list(definition.primary_key),
                        "display_columns": list(definition.display_columns),
                    }
                    for definition in DATASETS
                    if definition.section is section
                ],
            }
        )

    index_document = {
        "schema_version": "1.0",
        "snapshot_kind": "metadata",
        "instructions": [
            "Read manifest.json and index.json first.",
            "Do not recursively load the snapshot into context.",
            ("Search a dataset's index.jsonl, then read only the located line from rows.jsonl."),
        ],
        "sections": sections,
    }
    return RootDocuments(
        schema_json=_json_document(build_schema_document()),
        index_json=_json_document(index_document),
    )


def build_snapshot_archive(
    output: Path,
    *,
    snapshot_id: UUID,
    tenant_id: int,
    created_time: datetime,
    available_until: datetime,
    encoded_datasets: Sequence[EncodedDataset],
    max_archive_bytes: int,
) -> SnapshotArchive:
    """Create and verify one deterministic Metadata Snapshot ZIP."""
    if tenant_id <= 0:
        raise SnapshotContractError("tenant_id must be positive")
    if max_archive_bytes <= 0:
        raise SnapshotContractError("max_archive_bytes must be positive")
    created_at = _utc_timestamp("created_time", created_time)
    available_at = _utc_timestamp("available_until", available_until)
    if available_until <= created_time:
        raise SnapshotContractError("available_until must be after created_time")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing archive: {output.name}")

    roots = build_root_documents(encoded_datasets)
    encoded_by_name = {encoded.definition.name: encoded for encoded in encoded_datasets}
    members: list[tuple[str, bytes, int | None]] = [
        ("schema.json", roots.schema_json, None),
        ("index.json", roots.index_json, None),
    ]
    for definition in DATASETS:
        encoded = encoded_by_name[definition.name]
        _validate_encoded_dataset(encoded)
        members.extend(
            (
                (definition.index_path, encoded.index_jsonl, encoded.row_count),
                (definition.data_path, encoded.rows_jsonl, encoded.row_count),
            )
        )

    member_paths = [path for path, _content, _row_count in members]
    if len(member_paths) != len(set(member_paths)):
        raise SnapshotContractError("snapshot contains duplicate archive member paths")
    for member_path in member_paths:
        _validate_member_path(member_path)

    member_records = [
        {
            "path": member_path,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            **({"row_count": row_count} if row_count is not None else {}),
        }
        for member_path, content, row_count in members
    ]
    non_manifest_bytes = sum(len(content) for _path, content, _row_count in members)
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

    manifest_json = b""
    expanded_bytes = non_manifest_bytes
    for _attempt in range(4):
        manifest_document = {
            "schema_version": "1.0",
            "snapshot_kind": "metadata",
            "snapshot_id": str(snapshot_id),
            "tenant_id": str(tenant_id),
            "created_time": created_at,
            "available_until": available_at,
            "counts": {
                "physical_table_count": len(TABLES),
                "logical_dataset_count": len(DATASETS),
                "row_count": row_count,
                "file_count": len(members) + 1,
                "expanded_bytes": expanded_bytes,
            },
            "sections": section_counts,
            "schema": {
                "path": "schema.json",
                "sha256": hashlib.sha256(roots.schema_json).hexdigest(),
            },
            "index": {
                "path": "index.json",
                "sha256": hashlib.sha256(roots.index_json).hexdigest(),
            },
            "members": member_records,
        }
        manifest_json = _json_document(manifest_document)
        next_expanded_bytes = non_manifest_bytes + len(manifest_json)
        if next_expanded_bytes == expanded_bytes:
            break
        expanded_bytes = next_expanded_bytes
    else:
        raise SnapshotContractError("manifest expanded-byte count did not stabilize")

    if expanded_bytes > max_archive_bytes:
        raise SnapshotPayloadTooLargeError("snapshot expanded size exceeds the configured limit")

    archive_members = [("manifest.json", manifest_json, None), *members]
    archive_root = PurePosixPath("metadata-snapshot")
    created_output = False
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(
            output,
            "x",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            created_output = True
            for member_path, content, _row_count in archive_members:
                archive_path = (archive_root / member_path).as_posix()
                info = zipfile.ZipInfo(archive_path, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, content, compresslevel=9)

        size_bytes = output.stat().st_size
        if size_bytes > max_archive_bytes:
            raise SnapshotPayloadTooLargeError("snapshot archive size exceeds the configured limit")

        expected_names = [
            (archive_root / member_path).as_posix()
            for member_path, _content, _row_count in archive_members
        ]
        with zipfile.ZipFile(output, "r") as archive:
            if archive.namelist() != expected_names:
                raise SnapshotContractError("snapshot archive member validation failed")
            for member_path, content, _row_count in archive_members:
                archive_path = (archive_root / member_path).as_posix()
                if archive.read(archive_path) != content:
                    raise SnapshotContractError("snapshot archive content validation failed")

        with output.open("rb") as archive_file:
            archive_sha256 = hashlib.file_digest(archive_file, "sha256").hexdigest()
        return SnapshotArchive(
            path=output,
            size_bytes=size_bytes,
            expanded_bytes=expanded_bytes,
            row_count=row_count,
            sha256=archive_sha256,
        )
    except Exception:
        if created_output and output.is_file() and not output.is_symlink():
            output.unlink()
        raise


def _validate_encoded_dataset(encoded: EncodedDataset) -> None:
    table = TABLES_BY_NAME[encoded.definition.database_table]
    expected_columns = [column.name for column in table.columns]
    try:
        row_lines = encoded.rows_jsonl.decode("utf-8").splitlines()
        index_lines = encoded.index_jsonl.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise SnapshotContractError(f"{encoded.definition.name} JSONL is not valid UTF-8") from exc
    if encoded.rows_jsonl and not encoded.rows_jsonl.endswith(b"\n"):
        raise SnapshotContractError(f"{encoded.definition.name} rows JSONL lacks final newline")
    if encoded.index_jsonl and not encoded.index_jsonl.endswith(b"\n"):
        raise SnapshotContractError(f"{encoded.definition.name} index JSONL lacks final newline")
    if len(row_lines) != encoded.row_count or len(index_lines) != encoded.row_count:
        raise SnapshotContractError(f"{encoded.definition.name} JSONL row count is inconsistent")

    for line_number, (row_line, index_line) in enumerate(
        zip(row_lines, index_lines, strict=True),
        start=1,
    ):
        try:
            parsed_row: object = json.loads(row_line)
            parsed_locator: object = json.loads(index_line)
        except json.JSONDecodeError as exc:
            raise SnapshotContractError(
                f"{encoded.definition.name} contains invalid JSONL"
            ) from exc
        if not isinstance(parsed_row, dict):
            raise SnapshotContractError(
                f"{encoded.definition.name} rows JSONL violates column order"
            )
        untyped_row = cast(dict[object, object], parsed_row)
        if (
            not all(isinstance(key, str) for key in untyped_row)
            or list(untyped_row) != expected_columns
        ):
            raise SnapshotContractError(
                f"{encoded.definition.name} rows JSONL violates column order"
            )
        row = cast(dict[str, object], parsed_row)
        expected_primary_key = {
            column_name: row[column_name] for column_name in encoded.definition.primary_key
        }
        if not isinstance(parsed_locator, dict):
            raise SnapshotContractError(
                f"{encoded.definition.name} index JSONL contains an invalid locator"
            )
        untyped_locator = cast(dict[object, object], parsed_locator)
        if not all(isinstance(key, str) for key in untyped_locator):
            raise SnapshotContractError(
                f"{encoded.definition.name} index JSONL contains an invalid locator"
            )
        locator = cast(dict[str, object], parsed_locator)
        if locator != {
            "primary_key": expected_primary_key,
            "label": locator.get("label"),
            "file": "rows.jsonl",
            "line": line_number,
        }:
            raise SnapshotContractError(
                f"{encoded.definition.name} index JSONL contains an invalid locator"
            )
        label = locator["label"]
        if not isinstance(label, str) or not label or len(label) > 500 or "\n" in label:
            raise SnapshotContractError(
                f"{encoded.definition.name} index JSONL contains an invalid label"
            )


def _validate_member_path(member_path: str) -> None:
    path = PurePosixPath(member_path)
    if (
        not member_path
        or "\\" in member_path
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.parts[0].endswith(":")
    ):
        raise SnapshotContractError("snapshot contains an unsafe archive member path")


def _utc_timestamp(field_name: str, value: datetime) -> str:
    if value.utcoffset() is None:
        raise SnapshotContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _encode_column_value(
    dataset_name: str,
    column: ColumnDefinition,
    value: object,
) -> object:
    if value is None:
        if not column.nullable:
            raise SnapshotContractError(f"{dataset_name}.{column.name} cannot contain a null value")
        return None
    if column.type == "bigint":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SnapshotContractError(f"{dataset_name}.{column.name} must be a BIGINT")
        return str(value)
    if column.type == "bigint[]":
        if not isinstance(value, (list, tuple)):
            raise SnapshotContractError(f"{dataset_name}.{column.name} must be a BIGINT array")
        encoded_array: list[str | None] = []
        for element in cast(Sequence[object], value):
            if element is None:
                encoded_array.append(None)
            elif isinstance(element, bool) or not isinstance(element, int):
                raise SnapshotContractError(
                    f"{dataset_name}.{column.name} must contain only BIGINT values"
                )
            else:
                encoded_array.append(str(element))
        return encoded_array
    if column.type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SnapshotContractError(f"{dataset_name}.{column.name} must be an INTEGER")
        return value
    if column.type == "boolean":
        if not isinstance(value, bool):
            raise SnapshotContractError(f"{dataset_name}.{column.name} must be a BOOLEAN")
        return value
    if column.type in {"varchar", "text"}:
        if not isinstance(value, str):
            raise SnapshotContractError(f"{dataset_name}.{column.name} must be text")
        return value
    if column.type == "date":
        if isinstance(value, datetime) or not isinstance(value, date):
            raise SnapshotContractError(f"{dataset_name}.{column.name} must be a DATE")
        return value.isoformat()
    if column.type == "timestamptz":
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise SnapshotContractError(
                f"{dataset_name}.{column.name} must be a timezone-aware timestamp"
            )
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raise SnapshotContractError(f"{dataset_name}.{column.name} has an unsupported type")


def _primary_key_sort_key(
    definition: DatasetDefinition,
    table: TableDefinition,
    row: Mapping[str, object],
) -> tuple[int | str, ...]:
    columns_by_name = {column.name: column for column in table.columns}
    key: list[int | str] = []
    for column_name in definition.primary_key:
        value = row[column_name]
        if value is None:
            raise SnapshotContractError(f"{definition.name} primary key cannot be null")
        if columns_by_name[column_name].type == "bigint":
            if not isinstance(value, str):
                raise SnapshotContractError(
                    f"{definition.name} primary key has an invalid encoded type"
                )
            key.append(int(value))
        elif isinstance(value, (int, str)) and not isinstance(value, bool):
            key.append(value)
        else:
            raise SnapshotContractError(
                f"{definition.name} primary key has an unsupported encoded type"
            )
    return tuple(key)


def _index_label(definition: DatasetDefinition, row: Mapping[str, object]) -> str:
    values = [
        " ".join(str(row[column_name]).split())
        for column_name in definition.display_columns
        if row[column_name] is not None and " ".join(str(row[column_name]).split())
    ]
    if not values:
        values = [str(row[column_name]) for column_name in definition.primary_key]
    label = " · ".join(values)
    return label if len(label) <= 500 else f"{label[:499]}…"


def _json_line(value: object) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    )


def _json_document(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
