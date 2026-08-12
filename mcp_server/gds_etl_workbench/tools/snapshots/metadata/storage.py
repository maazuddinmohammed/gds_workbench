"""Private Azure Blob persistence for Metadata Snapshot archives."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from azure.core.exceptions import AzureError, ResourceExistsError, ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import BlobSasPermissions, ContentSettings, generate_blob_sas
from azure.storage.blob.aio import BlobServiceClient

from gds_etl_workbench.configuration import RuntimeSettings
from gds_etl_workbench.domain.errors import DependencyUnavailableError

from .archive import SnapshotArchive, SnapshotContractError


class MetadataSnapshotStore(Protocol):
    async def close(self) -> None: ...

    async def upload_archive(
        self,
        archive: SnapshotArchive,
        *,
        tenant_id: int,
        snapshot_id: UUID,
        created_at: datetime,
        available_until: datetime,
    ) -> None: ...

    async def create_read_url(
        self,
        *,
        tenant_id: int,
        snapshot_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> str | None: ...


class AzureMetadataSnapshotStore:
    """Create immutable private Blobs and mint bounded read-only SAS URLs."""

    def __init__(self, settings: RuntimeSettings) -> None:
        credential_options: dict[str, str] = {}
        if settings.metadata_snapshot_managed_identity_client_id is not None:
            credential_options["managed_identity_client_id"] = str(
                settings.metadata_snapshot_managed_identity_client_id
            )
        self._credential = DefaultAzureCredential(**credential_options)
        self._service = BlobServiceClient(
            account_url=settings.metadata_snapshot_storage_account_url,
            credential=self._credential,
        )
        account_name = self._service.account_name
        if not isinstance(account_name, str) or not account_name:
            raise SnapshotContractError("snapshot storage account identity is invalid")
        self._account_name = account_name
        self._container = settings.metadata_snapshot_storage_container

    async def close(self) -> None:
        await self._service.close()
        await self._credential.close()

    async def upload_archive(
        self,
        archive: SnapshotArchive,
        *,
        tenant_id: int,
        snapshot_id: UUID,
        created_at: datetime,
        available_until: datetime,
    ) -> None:
        _validate_identity(tenant_id, snapshot_id)
        created = _utc(created_at)
        available = _utc(available_until)
        if available <= created:
            raise SnapshotContractError("snapshot availability must follow creation time")
        blob = self._service.get_blob_client(
            container=self._container,
            blob=_blob_name(tenant_id, snapshot_id),
        )
        metadata = {
            "snapshot_kind": "metadata",
            "schema_version": "2.0",
            "tenant_id": str(tenant_id),
            "snapshot_id": str(snapshot_id),
            "created_time": _timestamp(created),
            "available_until": _timestamp(available),
            "size_bytes": str(archive.size_bytes),
            "sha256": archive.sha256,
        }
        try:
            with archive.path.open("rb") as archive_file:
                await blob.upload_blob(
                    archive_file,
                    length=archive.size_bytes,
                    overwrite=False,
                    metadata=metadata,
                    content_settings=ContentSettings(
                        content_type="application/zip",
                        content_disposition=(
                            f'attachment; filename="metadata-snapshot-{tenant_id}-'
                            f'{snapshot_id}.zip"'
                        ),
                    ),
                )
        except ResourceExistsError as exc:
            raise SnapshotContractError("snapshot Blob identity already exists") from exc
        except (AzureError, OSError) as exc:
            raise DependencyUnavailableError() from exc

    async def create_read_url(
        self,
        *,
        tenant_id: int,
        snapshot_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> str | None:
        _validate_identity(tenant_id, snapshot_id)
        current = _utc(now)
        if not 60 <= ttl_seconds <= 3600:
            raise SnapshotContractError("snapshot download TTL is invalid")
        blob_name = _blob_name(tenant_id, snapshot_id)
        blob = self._service.get_blob_client(container=self._container, blob=blob_name)
        try:
            properties = await blob.get_blob_properties()
            metadata = properties.metadata
            created_at = _parse_timestamp(metadata.get("created_time"))
            available_until = _parse_timestamp(metadata.get("available_until"))
            expected_disposition = (
                f'attachment; filename="metadata-snapshot-{tenant_id}-{snapshot_id}.zip"'
            )
            expected = {
                "snapshot_kind": "metadata",
                "schema_version": "2.0",
                "tenant_id": str(tenant_id),
                "snapshot_id": str(snapshot_id),
                "size_bytes": str(properties.size),
            }
            if (
                created_at is None
                or available_until is None
                or properties.size <= 0
                or created_at > current + timedelta(minutes=5)
                or available_until <= created_at
                or available_until - created_at > timedelta(hours=168)
                or available_until <= current
                or any(metadata.get(key) != value for key, value in expected.items())
                or not _is_sha256(metadata.get("sha256"))
                or properties.content_settings.content_type != "application/zip"
                or properties.content_settings.content_disposition != expected_disposition
            ):
                return None

            expires = min(
                current + timedelta(seconds=ttl_seconds),
                available_until,
            )
            starts = current - timedelta(minutes=5)
            delegation_key = await self._service.get_user_delegation_key(
                key_start_time=starts,
                key_expiry_time=expires,
            )
            sas = generate_blob_sas(
                account_name=self._account_name,
                container_name=self._container,
                blob_name=blob_name,
                user_delegation_key=delegation_key,
                permission=BlobSasPermissions(read=True),
                start=starts,
                expiry=expires,
                protocol="https",
            )
            return f"{blob.url}?{sas}"
        except ResourceNotFoundError:
            return None
        except (AzureError, ValueError) as exc:
            raise DependencyUnavailableError() from exc


def _blob_name(tenant_id: int, snapshot_id: UUID) -> str:
    _validate_identity(tenant_id, snapshot_id)
    return f"metadata/{tenant_id}/{snapshot_id}.zip"


def _validate_identity(tenant_id: int, snapshot_id: UUID) -> None:
    if tenant_id <= 0 or snapshot_id.version != 4:
        raise SnapshotContractError("snapshot identity is invalid")


def _utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise SnapshotContractError("snapshot timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.utcoffset() is not None else None


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
