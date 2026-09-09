"""Shared temporary-build, upload, and cleanup orchestration for Snapshots."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from gds_etl_workbench.domain.errors import DependencyUnavailableError

from .archive import SnapshotArchive, SnapshotContractError
from .storage import SnapshotKind, SnapshotStore

type ArchiveBuilder = Callable[[Path], SnapshotArchive]


@dataclass(frozen=True, slots=True)
class ReadySnapshot:
    snapshot_id: UUID
    scope_id: int
    created_at: datetime
    available_until: datetime
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SnapshotCreationWindow:
    snapshot_id: UUID
    created_at: datetime
    available_until: datetime


@dataclass(frozen=True, slots=True)
class SnapshotDownload:
    url: str
    expires_at: datetime


def create_snapshot_window(
    *,
    retention_hours: int,
    created_at: datetime | None = None,
    snapshot_id: UUID | None = None,
) -> SnapshotCreationWindow:
    """Validate and normalize the shared immutable Snapshot identity window."""
    requested_creation_time = created_at or datetime.now(UTC)
    identifier = snapshot_id or uuid4()
    if requested_creation_time.utcoffset() is None or identifier.version != 4:
        raise SnapshotContractError("snapshot creation identity is invalid")
    if not 1 <= retention_hours <= 168:
        raise SnapshotContractError("snapshot retention is invalid")
    created = requested_creation_time.astimezone(UTC)
    return SnapshotCreationWindow(
        snapshot_id=identifier,
        created_at=created,
        available_until=created + timedelta(hours=retention_hours),
    )


async def create_snapshot_download(
    store: SnapshotStore,
    *,
    snapshot_kind: SnapshotKind,
    scope_id: int,
    schema_version: str,
    snapshot_id: UUID,
    available_until: datetime,
    now: datetime,
    ttl_seconds: int,
) -> SnapshotDownload:
    """Mint one bounded read-only URL for an existing immutable Snapshot."""
    download_url = await store.create_read_url(
        snapshot_kind=snapshot_kind,
        scope_id=scope_id,
        schema_version=schema_version,
        snapshot_id=snapshot_id,
        now=now,
        ttl_seconds=ttl_seconds,
    )
    if download_url is None:
        raise DependencyUnavailableError()
    return SnapshotDownload(
        url=download_url,
        expires_at=min(
            available_until,
            now + timedelta(seconds=ttl_seconds),
        ),
    )


async def build_and_upload_snapshot(
    store: SnapshotStore,
    *,
    snapshot_kind: SnapshotKind,
    scope_id: int,
    schema_version: str,
    snapshot_id: UUID,
    created_at: datetime,
    available_until: datetime,
    build_archive: ArchiveBuilder,
) -> ReadySnapshot:
    """Build privately, upload immutably, and retain no local Snapshot files."""
    with TemporaryDirectory(prefix=f"gds-{snapshot_kind}-snapshot-") as temporary_directory:
        archive = await asyncio.to_thread(
            build_archive,
            Path(temporary_directory) / f"{snapshot_kind}-snapshot.zip",
        )
        await store.upload_archive(
            archive,
            snapshot_kind=snapshot_kind,
            scope_id=scope_id,
            schema_version=schema_version,
            snapshot_id=snapshot_id,
            created_at=created_at,
            available_until=available_until,
        )
        return ReadySnapshot(
            snapshot_id=snapshot_id,
            scope_id=scope_id,
            created_at=created_at,
            available_until=available_until,
            size_bytes=archive.size_bytes,
            sha256=archive.sha256,
        )
