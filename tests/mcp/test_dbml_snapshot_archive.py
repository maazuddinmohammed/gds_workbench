from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from test_dbml_snapshot_renderer import _snapshot

from gds_etl_workbench.tools.snapshots.archive import SnapshotPayloadTooLargeError
from gds_etl_workbench.tools.snapshots.dbml.archive import build_dbml_snapshot_archive
from gds_etl_workbench.tools.snapshots.dbml.renderer import render_dbml_documents

SNAPSHOT_ID = UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233")
CREATED_TIME = datetime(2026, 8, 15, 16, 0, tzinfo=UTC)
AVAILABLE_UNTIL = CREATED_TIME + timedelta(hours=24)


def test_dbml_archive_contains_manifest_and_bounded_files(tmp_path: Path) -> None:
    snapshot = _snapshot()
    documents = render_dbml_documents(
        snapshot,
        model_type="full",
        include_submodels=True,
    )
    output = tmp_path / "dbml.zip"

    result = build_dbml_snapshot_archive(
        output,
        snapshot_id=SNAPSHOT_ID,
        snapshot=snapshot,
        model_type="full",
        include_submodels=True,
        documents=documents,
        created_time=CREATED_TIME,
        available_until=AVAILABLE_UNTIL,
        max_archive_bytes=20 * 1024 * 1024,
    )

    assert result.sha256 == hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == [
            "model-dbml/manifest.json",
            *(f"model-dbml/files/{document.path}" for document in documents),
        ]
        manifest = json.loads(archive.read("model-dbml/manifest.json"))
        assert manifest["schema_version"] == "2.0"
        assert manifest["snapshot_kind"] == "dbml"
        assert manifest["database_ids_included"] is False
        assert manifest["model_id"] == 1
        assert manifest["model_revision"] == 2
        assert manifest["model_type"] == "full"
        assert manifest["include_submodels"] is True
        assert manifest["counts"]["dbml_file_count"] == 5
        assert manifest["counts"]["file_count"] == 6
        assert manifest["counts"]["expanded_bytes"] == sum(
            info.file_size for info in archive.infolist()
        )
        for file_record in manifest["files"]:
            content = archive.read(f"model-dbml/{file_record['path']}")
            assert file_record["sha256"] == hashlib.sha256(content).hexdigest()
            assert file_record["size_bytes"] == len(content)


def test_dbml_archive_is_deterministic_and_enforces_size_limit(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot()
    documents = render_dbml_documents(
        snapshot,
        model_type="logical",
        include_submodels=True,
    )
    arguments = {
        "snapshot_id": SNAPSHOT_ID,
        "snapshot": snapshot,
        "model_type": "logical",
        "include_submodels": True,
        "created_time": CREATED_TIME,
        "available_until": AVAILABLE_UNTIL,
    }

    first = build_dbml_snapshot_archive(
        tmp_path / "first.zip",
        documents=documents,
        max_archive_bytes=20 * 1024 * 1024,
        **arguments,
    )
    second = build_dbml_snapshot_archive(
        tmp_path / "second.zip",
        documents=tuple(reversed(documents)),
        max_archive_bytes=20 * 1024 * 1024,
        **arguments,
    )

    assert first.sha256 == second.sha256
    assert first.path.read_bytes() == second.path.read_bytes()
    with pytest.raises(SnapshotPayloadTooLargeError, match="expanded size"):
        build_dbml_snapshot_archive(
            tmp_path / "oversized.zip",
            documents=documents,
            max_archive_bytes=1,
            **arguments,
        )
    assert not (tmp_path / "oversized.zip").exists()
