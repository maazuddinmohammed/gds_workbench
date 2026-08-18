from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from gds_etl_workbench.configuration import AuthMode, Environment, RuntimeSettings
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.tools.snapshots import storage as storage_module
from gds_etl_workbench.tools.snapshots.metadata.archive import (
    SnapshotArchive,
    encode_dataset,
)
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    build_and_upload_metadata_snapshot,
)
from gds_etl_workbench.tools.snapshots.storage import AzureSnapshotStore

SNAPSHOT_ID = UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233")
CREATED_AT = datetime(2026, 8, 11, 16, 0, tzinfo=UTC)
AVAILABLE_UNTIL = CREATED_AT + timedelta(hours=24)


class FakeCredential:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeBlob:
    def __init__(self) -> None:
        self.url = "https://snapshot.blob.core.windows.net/snapshots/blob.zip"
        self.upload: dict[str, Any] | None = None
        self.properties: object | None = None

    async def upload_blob(self, data: Any, **kwargs: Any) -> dict[str, Any]:
        self.upload = {"content": data.read(), **kwargs}
        return {}

    async def get_blob_properties(self) -> object:
        assert self.properties is not None
        return self.properties


class FakeBlobService:
    account_name = "snapshot"

    def __init__(self, blob: FakeBlob) -> None:
        self.blob = blob
        self.closed = False
        self.requested_container: str | None = None
        self.requested_blob: str | None = None
        self.delegation_request: tuple[datetime, datetime] | None = None

    def get_blob_client(self, *, container: str, blob: str) -> FakeBlob:
        self.requested_container = container
        self.requested_blob = blob
        return self.blob

    async def get_user_delegation_key(
        self,
        key_start_time: datetime,
        key_expiry_time: datetime,
    ) -> object:
        self.delegation_request = (key_start_time, key_expiry_time)
        return object()

    async def close(self) -> None:
        self.closed = True


class RecordingStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.archive_path: Path | None = None
        self.archive_content = b""

    async def close(self) -> None:
        return None

    async def upload_archive(
        self,
        archive: SnapshotArchive,
        *,
        snapshot_kind: str,
        scope_id: int,
        schema_version: str,
        snapshot_id: UUID,
        created_at: datetime,
        available_until: datetime,
    ) -> None:
        self.archive_path = archive.path
        assert archive.path.is_file()
        assert snapshot_kind == "metadata"
        assert scope_id == 123
        assert schema_version == "2.0"
        assert snapshot_id == SNAPSHOT_ID
        assert created_at == CREATED_AT
        assert available_until == AVAILABLE_UNTIL
        self.archive_content = archive.path.read_bytes()
        if self.fail:
            raise DependencyUnavailableError()

    async def create_read_url(
        self,
        *,
        snapshot_kind: str,
        scope_id: int,
        schema_version: str,
        snapshot_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> str | None:
        raise AssertionError("not used by archive orchestration")


@pytest.mark.asyncio
async def test_archive_upload_uses_temporary_file_and_always_removes_it() -> None:
    store = RecordingStore()
    encoded = tuple(encode_dataset(dataset, []) for dataset in DATASETS)

    ready = await build_and_upload_metadata_snapshot(
        encoded,
        store,
        tenant_id=123,
        tenant_code="TENANT",
        snapshot_id=SNAPSHOT_ID,
        created_at=CREATED_AT,
        available_until=AVAILABLE_UNTIL,
        max_archive_bytes=268435456,
    )

    assert ready.snapshot_id == SNAPSHOT_ID
    assert ready.size_bytes == len(store.archive_content)
    assert store.archive_path is not None
    assert not store.archive_path.exists()
    assert not store.archive_path.parent.exists()


@pytest.mark.asyncio
async def test_archive_upload_failure_also_removes_temporary_file() -> None:
    store = RecordingStore(fail=True)
    encoded = tuple(encode_dataset(dataset, []) for dataset in DATASETS)

    with pytest.raises(DependencyUnavailableError):
        await build_and_upload_metadata_snapshot(
            encoded,
            store,
            tenant_id=123,
            tenant_code="TENANT",
            snapshot_id=SNAPSHOT_ID,
            created_at=CREATED_AT,
            available_until=AVAILABLE_UNTIL,
            max_archive_bytes=268435456,
        )

    assert store.archive_path is not None
    assert not store.archive_path.exists()
    assert not store.archive_path.parent.exists()


@pytest.mark.asyncio
async def test_azure_store_uploads_create_only_and_mints_read_only_sas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = FakeCredential()
    blob = FakeBlob()
    service = FakeBlobService(blob)
    sas_arguments: dict[str, Any] = {}
    monkeypatch.setattr(
        storage_module, "DefaultAzureCredential", lambda **_kwargs: credential
    )
    monkeypatch.setattr(storage_module, "BlobServiceClient", lambda **_kwargs: service)

    def fake_generate_blob_sas(**kwargs: Any) -> str:
        sas_arguments.update(kwargs)
        return "sv=fake&sp=r&sig=secret"

    monkeypatch.setattr(storage_module, "generate_blob_sas", fake_generate_blob_sas)
    settings = _settings()
    store = AzureSnapshotStore(settings)
    archive_path = tmp_path / "snapshot.zip"
    archive_path.write_bytes(b"archive")
    archive = SnapshotArchive(
        path=archive_path,
        size_bytes=7,
        expanded_bytes=9,
        row_count=0,
        sha256="a" * 64,
    )

    await store.upload_archive(
        archive,
        snapshot_kind="metadata",
        scope_id=123,
        schema_version="2.0",
        snapshot_id=SNAPSHOT_ID,
        created_at=CREATED_AT,
        available_until=AVAILABLE_UNTIL,
    )

    assert service.requested_container == "snapshots"
    assert service.requested_blob == f"metadata/123/{SNAPSHOT_ID}.zip"
    assert blob.upload is not None
    assert blob.upload["content"] == b"archive"
    assert blob.upload["overwrite"] is False
    assert blob.upload["length"] == 7
    assert blob.upload["metadata"] == {
        "snapshot_kind": "metadata",
        "schema_version": "2.0",
        "tenant_id": "123",
        "snapshot_id": str(SNAPSHOT_ID),
        "created_time": "2026-08-11T16:00:00Z",
        "available_until": "2026-08-12T16:00:00Z",
        "size_bytes": "7",
        "sha256": "a" * 64,
    }
    content_settings = blob.upload["content_settings"]
    assert content_settings.content_type == "application/zip"
    assert content_settings.content_disposition == (
        f'attachment; filename="metadata-snapshot-123-{SNAPSHOT_ID}.zip"'
    )

    blob.properties = SimpleNamespace(
        metadata=blob.upload["metadata"],
        size=7,
        content_settings=SimpleNamespace(
            content_type="application/zip",
            content_disposition=(
                f'attachment; filename="metadata-snapshot-123-{SNAPSHOT_ID}.zip"'
            ),
        ),
    )
    read_url = await store.create_read_url(
        snapshot_kind="metadata",
        scope_id=123,
        schema_version="2.0",
        snapshot_id=SNAPSHOT_ID,
        now=CREATED_AT,
        ttl_seconds=900,
    )

    assert read_url == f"{blob.url}?sv=fake&sp=r&sig=secret"
    assert str(sas_arguments["permission"]) == "r"
    assert sas_arguments["protocol"] == "https"
    assert service.delegation_request is not None
    assert service.delegation_request[1] == CREATED_AT + timedelta(seconds=900)

    service.delegation_request = None
    blob.properties.metadata = {
        **blob.upload["metadata"],
        "available_until": "2026-08-11T16:00:00Z",
    }
    assert (
        await store.create_read_url(
            snapshot_kind="metadata",
            scope_id=123,
            schema_version="2.0",
            snapshot_id=SNAPSHOT_ID,
            now=CREATED_AT,
            ttl_seconds=900,
        )
        is None
    )
    assert service.delegation_request is None

    await store.close()
    assert service.closed is True
    assert credential.closed is True


def _settings() -> RuntimeSettings:
    return RuntimeSettings(
        environment=Environment.LOCAL,
        auth_mode=AuthMode.DEV,
        database_dsn="postgresql://unused.invalid/workbench",
        cursor_signing_key=b"development-only-key-32-bytes-long",
        allowed_hosts=("testserver",),
        mcp_public_url="https://workbench.example.test/mcp",
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_api_client_id=UUID("22222222-2222-2222-2222-222222222222"),
        local_principal_object_id=UUID("33333333-3333-3333-3333-333333333333"),
        require_https=False,
        schema_version="1.0.0",
        pool_min=1,
        pool_max=2,
        pool_timeout_seconds=5,
        metadata_snapshot_storage_account_url="https://snapshot.blob.core.windows.net",
        metadata_snapshot_storage_container="snapshots",
        metadata_snapshot_download_ttl_seconds=900,
        metadata_snapshot_retention_hours=24,
        metadata_snapshot_max_archive_bytes=268435456,
        metadata_snapshot_managed_identity_client_id=None,
    )
