"""Shared deterministic ZIP writer for all governed Snapshot kinds."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


class SnapshotContractError(ValueError):
    """A safe failure caused by invalid Snapshot input or schema drift."""


class SnapshotPayloadTooLargeError(SnapshotContractError):
    """The validated expanded or compressed Snapshot exceeds its fixed limit."""


@dataclass(frozen=True, slots=True)
class SnapshotArchive:
    path: Path
    size_bytes: int
    expanded_bytes: int
    row_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SnapshotMember:
    path: str
    content: bytes
    row_count: int | None = None


type ManifestBuilder = Callable[
    [tuple[dict[str, object], ...], int],
    Mapping[str, object],
]


def write_snapshot_archive(
    output: Path,
    *,
    archive_root: str,
    members: Sequence[SnapshotMember],
    row_count: int,
    max_archive_bytes: int,
    build_manifest: ManifestBuilder,
) -> SnapshotArchive:
    """Write, verify, and hash one immutable deterministic Snapshot ZIP."""
    if max_archive_bytes <= 0:
        raise SnapshotContractError("max_archive_bytes must be positive")
    if row_count < 0:
        raise SnapshotContractError("snapshot row_count cannot be negative")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing archive: {output.name}")
    _validate_member_path(archive_root)

    member_paths = [member.path for member in members]
    if len(member_paths) != len(set(member_paths)):
        raise SnapshotContractError("snapshot contains duplicate archive member paths")
    for member_path in member_paths:
        _validate_member_path(member_path)

    member_records: tuple[dict[str, object], ...] = tuple(
        {
            "path": member.path,
            "sha256": hashlib.sha256(member.content).hexdigest(),
            "size_bytes": len(member.content),
            **({"row_count": member.row_count} if member.row_count is not None else {}),
        }
        for member in members
    )
    non_manifest_bytes = sum(len(member.content) for member in members)
    expanded_bytes = non_manifest_bytes
    manifest_json = b""
    for _attempt in range(4):
        manifest_json = json_document(build_manifest(member_records, expanded_bytes))
        next_expanded_bytes = non_manifest_bytes + len(manifest_json)
        if next_expanded_bytes == expanded_bytes:
            break
        expanded_bytes = next_expanded_bytes
    else:
        raise SnapshotContractError("manifest expanded-byte count did not stabilize")

    if expanded_bytes > max_archive_bytes:
        raise SnapshotPayloadTooLargeError("snapshot expanded size exceeds the configured limit")

    archive_members = (SnapshotMember("manifest.json", manifest_json), *members)
    root = PurePosixPath(archive_root)
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
            for member in archive_members:
                archive_path = (root / member.path).as_posix()
                info = zipfile.ZipInfo(archive_path, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, member.content, compresslevel=9)

        size_bytes = output.stat().st_size
        if size_bytes > max_archive_bytes:
            raise SnapshotPayloadTooLargeError("snapshot archive size exceeds the configured limit")

        expected_names = [(root / member.path).as_posix() for member in archive_members]
        with zipfile.ZipFile(output, "r") as archive:
            if archive.namelist() != expected_names:
                raise SnapshotContractError("snapshot archive member validation failed")
            for member in archive_members:
                if archive.read((root / member.path).as_posix()) != member.content:
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


def utc_timestamp(field_name: str, value: datetime) -> str:
    if value.utcoffset() is None:
        raise SnapshotContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def json_line(value: object) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    )


def json_document(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
