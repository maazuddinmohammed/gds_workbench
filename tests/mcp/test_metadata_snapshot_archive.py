from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from gds_etl_workbench.tools.snapshots.metadata.archive import (
    EncodedDataset,
    SnapshotArchive,
    SnapshotContractError,
    build_snapshot_archive,
    encode_dataset,
)
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS

SNAPSHOT_ID = UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233")
CREATED_TIME = datetime(2026, 8, 11, 16, 0, tzinfo=UTC)
AVAILABLE_UNTIL = CREATED_TIME + timedelta(hours=24)


def encoded_datasets(*, include_project: bool = False) -> tuple[EncodedDataset, ...]:
    encoded = [encode_dataset(definition, []) for definition in DATASETS]
    if include_project:
        encoded[0] = encode_dataset(
            DATASETS[0],
            [
                {
                    "project_code": "RISK",
                    "project_name": "Risk Analytics",
                    "project_description": None,
                    "is_active": True,
                }
            ],
        )
    return tuple(encoded)


def build(output: Path, datasets: tuple[EncodedDataset, ...]) -> SnapshotArchive:
    return build_snapshot_archive(
        output,
        snapshot_id=SNAPSHOT_ID,
        tenant_code="TENANT",
        created_time=CREATED_TIME,
        available_until=AVAILABLE_UNTIL,
        encoded_datasets=datasets,
        max_archive_bytes=268435456,
    )


def test_snapshot_archive_manifest_hashes_counts_and_safe_members(
    tmp_path: Path,
) -> None:
    output = tmp_path / "metadata.zip"
    result = build(output, encoded_datasets(include_project=True))

    assert result.path == output
    assert result.size_bytes == output.stat().st_size
    assert result.row_count == 1
    assert result.sha256 == hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as archive:
        infos = archive.infolist()
        names = archive.namelist()
        manifest = json.loads(archive.read("metadata-snapshot/manifest.json"))
        assert len(names) == 70
        assert names[0] == "metadata-snapshot/manifest.json"
        assert all(name.startswith("metadata-snapshot/") for name in names)
        assert all(".." not in name.split("/") and "\\" not in name for name in names)
        assert all(not info.is_dir() for info in infos)
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
        assert all(stat.S_IFMT(info.external_attr >> 16) == stat.S_IFREG for info in infos)

        assert manifest["snapshot_id"] == str(SNAPSHOT_ID)
        assert manifest["tenant_code"] == "TENANT"
        assert manifest["database_ids_included"] is False
        assert manifest["schema_version"] == "2.0"
        assert manifest["generated_at"] == "2026-08-11T16:00:00Z"
        assert "created_time" not in manifest
        assert manifest["available_until"] == "2026-08-12T16:00:00Z"
        assert manifest["counts"] == {
            "physical_table_count": 23,
            "logical_dataset_count": 29,
            "lookup_file_count": 10,
            "row_count": 1,
            "file_count": 70,
            "expanded_bytes": sum(info.file_size for info in infos),
        }
        assert manifest["sections"] == {
            "foundation": {"dataset_count": 13, "row_count": 1},
            "metadata": {"dataset_count": 16, "row_count": 0},
        }
        assert len(manifest["members"]) == 69
        for member in manifest["members"]:
            content = archive.read(f"metadata-snapshot/{member['path']}")
            assert member["size_bytes"] == len(content)
            assert member["sha256"] == hashlib.sha256(content).hexdigest()
        assert manifest["catalog"] == {
            "path": "catalog.json",
            "sha256": hashlib.sha256(archive.read("metadata-snapshot/catalog.json")).hexdigest(),
        }
        assert manifest["schemas"] == {
            "directory": "schemas",
            "dataset_count": 29,
        }
    assert result.expanded_bytes == manifest["counts"]["expanded_bytes"]


def test_snapshot_archive_is_deterministic(tmp_path: Path) -> None:
    first_path = tmp_path / "first.zip"
    second_path = tmp_path / "second.zip"
    datasets = encoded_datasets(include_project=True)

    first = build(first_path, datasets)
    second = build(second_path, tuple(reversed(datasets)))

    assert first.sha256 == second.sha256
    assert first_path.read_bytes() == second_path.read_bytes()


def test_snapshot_archive_rejects_inconsistent_or_oversized_content(
    tmp_path: Path,
) -> None:
    datasets = encoded_datasets()
    inconsistent = (replace(datasets[0], row_count=1), *datasets[1:])

    with pytest.raises(SnapshotContractError, match="row count is inconsistent"):
        build(tmp_path / "inconsistent.zip", inconsistent)
    assert not (tmp_path / "inconsistent.zip").exists()

    with pytest.raises(SnapshotContractError, match="expanded size"):
        build_snapshot_archive(
            tmp_path / "oversized.zip",
            snapshot_id=SNAPSHOT_ID,
            tenant_code="TENANT",
            created_time=CREATED_TIME,
            available_until=AVAILABLE_UNTIL,
            encoded_datasets=datasets,
            max_archive_bytes=1,
        )
    assert not (tmp_path / "oversized.zip").exists()


def test_snapshot_archive_refuses_overwrite_and_invalid_availability(
    tmp_path: Path,
) -> None:
    output = tmp_path / "owned.zip"
    output.write_bytes(b"owner content")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        build(output, encoded_datasets())
    assert output.read_bytes() == b"owner content"

    with pytest.raises(SnapshotContractError, match="must be after"):
        build_snapshot_archive(
            tmp_path / "invalid-time.zip",
            snapshot_id=SNAPSHOT_ID,
            tenant_code="TENANT",
            created_time=CREATED_TIME,
            available_until=CREATED_TIME,
            encoded_datasets=encoded_datasets(),
            max_archive_bytes=268435456,
        )
