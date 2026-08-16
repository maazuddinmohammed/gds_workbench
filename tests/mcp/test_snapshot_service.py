from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.tools.snapshots.archive import (
    SnapshotArchive,
    SnapshotContractError,
)
from gds_etl_workbench.tools.snapshots.service import (
    create_snapshot_download,
    create_snapshot_window,
)
from gds_etl_workbench.tools.snapshots.storage import SnapshotKind


class FakeSnapshotStore:
    def __init__(self, url: str | None) -> None:
        self.url = url
        self.read_calls: list[dict[str, object]] = []

    async def close(self) -> None:
        pass

    async def upload_archive(
        self,
        archive: SnapshotArchive,
        *,
        snapshot_kind: SnapshotKind,
        scope_id: int,
        schema_version: str,
        snapshot_id: UUID,
        created_at: datetime,
        available_until: datetime,
    ) -> None:
        raise AssertionError("upload is not used by these tests")

    async def create_read_url(
        self,
        *,
        snapshot_kind: SnapshotKind,
        scope_id: int,
        schema_version: str,
        snapshot_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> str | None:
        self.read_calls.append(
            {
                "snapshot_kind": snapshot_kind,
                "scope_id": scope_id,
                "schema_version": schema_version,
                "snapshot_id": snapshot_id,
                "now": now,
                "ttl_seconds": ttl_seconds,
            }
        )
        return self.url


def test_create_snapshot_window_normalizes_one_shared_creation_window() -> None:
    snapshot_id = UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233")
    created_at = datetime(2026, 8, 15, 12, tzinfo=timezone(timedelta(hours=-4)))

    window = create_snapshot_window(
        retention_hours=24,
        created_at=created_at,
        snapshot_id=snapshot_id,
    )

    assert window.snapshot_id == snapshot_id
    assert window.created_at == datetime(2026, 8, 15, 16, tzinfo=UTC)
    assert window.available_until == datetime(2026, 8, 16, 16, tzinfo=UTC)


@pytest.mark.parametrize("retention_hours", [0, 169])
def test_create_snapshot_window_rejects_invalid_retention(retention_hours: int) -> None:
    with pytest.raises(SnapshotContractError, match="snapshot retention is invalid"):
        create_snapshot_window(
            retention_hours=retention_hours,
            created_at=datetime(2026, 8, 15, tzinfo=UTC),
            snapshot_id=UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233"),
        )


@pytest.mark.asyncio
async def test_create_snapshot_download_caps_expiry_at_snapshot_retention() -> None:
    store = FakeSnapshotStore("https://example.invalid/read")
    now = datetime(2026, 8, 15, 16, tzinfo=UTC)
    snapshot_id = UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233")

    download = await create_snapshot_download(
        store,
        snapshot_kind="model",
        scope_id=42,
        schema_version="2.0",
        snapshot_id=snapshot_id,
        available_until=now + timedelta(minutes=5),
        now=now,
        ttl_seconds=3600,
    )

    assert download.url == "https://example.invalid/read"
    assert download.expires_at == now + timedelta(minutes=5)
    assert store.read_calls == [
        {
            "snapshot_kind": "model",
            "scope_id": 42,
            "schema_version": "2.0",
            "snapshot_id": snapshot_id,
            "now": now,
            "ttl_seconds": 3600,
        }
    ]


@pytest.mark.asyncio
async def test_create_snapshot_download_rejects_missing_blob() -> None:
    now = datetime(2026, 8, 15, 16, tzinfo=UTC)

    with pytest.raises(DependencyUnavailableError):
        await create_snapshot_download(
            FakeSnapshotStore(None),
            snapshot_kind="metadata",
            scope_id=42,
            schema_version="2.0",
            snapshot_id=UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233"),
            available_until=now + timedelta(hours=1),
            now=now,
            ttl_seconds=300,
        )
