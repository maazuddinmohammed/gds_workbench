"""Run one safe, read-only Metadata Snapshot diagnostic."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal, cast
from uuid import uuid4

from azure.core.exceptions import AzureError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import ConfigurationError, RuntimeSettings
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import PostgresDatabase, ReadIsolation
from gds_etl_workbench.tools.snapshots.archive import SnapshotContractError
from gds_etl_workbench.tools.snapshots.metadata.archive import build_snapshot_archive
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    select_snapshot_datasets,
)

_CONFIGURATION_PATH = "gds_etl_workbench/configuration.py"
_METADATA_SNAPSHOT_PATH = "gds_etl_workbench/tools/snapshots/metadata/get_metadata_snapshot.py"
_SAFE_DETAIL = re.compile(r"[^A-Za-z0-9_ .,:()/'=-]")
_DEPLOYMENT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class DeploymentInspection:
    status: Literal["OK", "FAILED"]
    file_count: int
    missing_count: int
    mismatch_count: int
    unlisted_python_count: int
    manifest_sha256: str | None
    configuration_actual_sha256: str | None
    configuration_expected_sha256: str | None
    configuration_matches: bool
    metadata_snapshot_actual_sha256: str | None
    metadata_snapshot_expected_sha256: str | None
    metadata_snapshot_matches: bool
    reason: str | None = None


def _failed_inspection(reason: str, manifest_sha256: str | None = None) -> DeploymentInspection:
    return DeploymentInspection(
        status="FAILED",
        file_count=0,
        missing_count=0,
        mismatch_count=0,
        unlisted_python_count=0,
        manifest_sha256=manifest_sha256,
        configuration_actual_sha256=None,
        configuration_expected_sha256=None,
        configuration_matches=False,
        metadata_snapshot_actual_sha256=None,
        metadata_snapshot_expected_sha256=None,
        metadata_snapshot_matches=False,
        reason=reason,
    )


def inspect_deployment(root: Path) -> DeploymentInspection:
    """Check every manifest file and report only hashes and bounded counts."""
    manifest_path = root / "BUILD_MANIFEST.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return _failed_inspection("manifest_missing")
    try:
        manifest_content = manifest_path.read_bytes()
        raw_manifest: object = json.loads(manifest_content)
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return _failed_inspection("manifest_unreadable")

    manifest_sha256 = hashlib.sha256(manifest_content).hexdigest()
    if not isinstance(raw_manifest, dict):
        return _failed_inspection("manifest_invalid", manifest_sha256)
    manifest = cast(dict[str, object], raw_manifest)
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        return _failed_inspection("manifest_invalid", manifest_sha256)
    files = cast(list[object], raw_files)

    records: dict[str, tuple[int, str]] = {}
    for raw_item in files:
        if not isinstance(raw_item, dict):
            return _failed_inspection("manifest_invalid", manifest_sha256)
        item = cast(dict[str, object], raw_item)
        relative = item.get("path")
        size = item.get("size")
        expected_sha256 = item.get("sha256")
        if not isinstance(relative, str):
            return _failed_inspection("manifest_invalid", manifest_sha256)
        pure_path = PurePosixPath(relative)
        if (
            pure_path.is_absolute()
            or ".." in pure_path.parts
            or relative in records
            or type(size) is not int
            or size < 0
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            return _failed_inspection("manifest_invalid", manifest_sha256)
        records[relative] = (size, expected_sha256)

    missing_count = 0
    mismatch_count = 0
    actual_hashes: dict[str, str] = {}
    for relative, (expected_size, expected_sha256) in records.items():
        deployed = root.joinpath(*PurePosixPath(relative).parts)
        if deployed.is_symlink() or not deployed.is_file():
            missing_count += 1
            continue
        try:
            content = deployed.read_bytes()
        except OSError:
            missing_count += 1
            continue
        actual_sha256 = hashlib.sha256(content).hexdigest()
        actual_hashes[relative] = actual_sha256
        if len(content) != expected_size or actual_sha256 != expected_sha256:
            mismatch_count += 1

    listed_paths = set(records)
    package = root / "gds_etl_workbench"
    unlisted_python_count = 0
    if package.is_dir():
        for path in package.rglob("*.py"):
            if "__pycache__" in path.parts or path.is_symlink() or not path.is_file():
                continue
            if path.relative_to(root).as_posix() not in listed_paths:
                unlisted_python_count += 1

    configuration_expected = records.get(_CONFIGURATION_PATH, (0, None))[1]
    metadata_snapshot_expected = records.get(_METADATA_SNAPSHOT_PATH, (0, None))[1]
    configuration_actual = actual_hashes.get(_CONFIGURATION_PATH)
    metadata_snapshot_actual = actual_hashes.get(_METADATA_SNAPSHOT_PATH)
    configuration_matches = (
        configuration_expected is not None and configuration_actual == configuration_expected
    )
    metadata_snapshot_matches = (
        metadata_snapshot_expected is not None
        and metadata_snapshot_actual == metadata_snapshot_expected
    )
    failed = (
        missing_count > 0
        or mismatch_count > 0
        or unlisted_python_count > 0
        or not configuration_matches
        or not metadata_snapshot_matches
    )
    return DeploymentInspection(
        status="FAILED" if failed else "OK",
        file_count=len(records),
        missing_count=missing_count,
        mismatch_count=mismatch_count,
        unlisted_python_count=unlisted_python_count,
        manifest_sha256=manifest_sha256,
        configuration_actual_sha256=configuration_actual,
        configuration_expected_sha256=configuration_expected,
        configuration_matches=configuration_matches,
        metadata_snapshot_actual_sha256=metadata_snapshot_actual,
        metadata_snapshot_expected_sha256=metadata_snapshot_expected,
        metadata_snapshot_matches=metadata_snapshot_matches,
    )


def _safe_text(value: object, *, maximum: int = 240) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ")[:maximum]
    return _SAFE_DETAIL.sub("?", text)


def _cause_fields(error: BaseException) -> str:
    cause = error.__cause__
    if cause is None:
        return ""
    fields = f" cause_type={type(cause).__name__}"
    sqlstate = getattr(cause, "sqlstate", None)
    if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate):
        fields += f" sqlstate={sqlstate}"
    return fields


def _failure(stage: str, error: BaseException) -> None:
    if isinstance(error, (ConfigurationError, SnapshotContractError)):
        print(f"{stage}=FAILED type={type(error).__name__} detail={_safe_text(error)}")
        return
    if isinstance(error, WorkbenchError):
        print(
            f"{stage}=FAILED type={type(error).__name__} code={_safe_text(error.code)}"
            f"{_cause_fields(error)}"
        )
        return
    if isinstance(error, AzureError):
        fields = f"{stage}=FAILED type={type(error).__name__}"
        status_code = getattr(error, "status_code", None)
        error_code = getattr(error, "error_code", None)
        if isinstance(status_code, int):
            fields += f" status_code={status_code}"
        if isinstance(error_code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", error_code):
            fields += f" error_code={error_code}"
        print(fields)
        return
    print(f"{stage}=FAILED type={type(error).__name__}{_cause_fields(error)}")


def load_settings_for_diagnostic(
    source: Mapping[str, str],
) -> tuple[RuntimeSettings | None, bool]:
    try:
        settings = RuntimeSettings.from_environment(source)
        print("configuration=OK")
        return settings, True
    except ConfigurationError as error:
        _failure("configuration", error)

    if (
        source.get("GDS_ENVIRONMENT", "").strip() == "production"
        and source.get("GDS_LOCAL_PRINCIPAL_OBJECT_ID", "").strip()
    ):
        diagnostic_values = dict(source)
        diagnostic_values.pop("GDS_LOCAL_PRINCIPAL_OBJECT_ID")
        try:
            settings = RuntimeSettings.from_environment(diagnostic_values)
            print("configuration_recovery=OK action=ignored_local_principal_in_temporary_copy")
            return settings, False
        except ConfigurationError as recovery_error:
            _failure("configuration_recovery", recovery_error)
    return None, False


async def _check_storage(settings: RuntimeSettings) -> bool:
    credential_options: dict[str, str] = {}
    if settings.metadata_snapshot_managed_identity_client_id is not None:
        credential_options["managed_identity_client_id"] = str(
            settings.metadata_snapshot_managed_identity_client_id
        )
    credential = DefaultAzureCredential(**credential_options)
    service = BlobServiceClient(
        account_url=settings.metadata_snapshot_storage_account_url,
        credential=credential,
    )
    succeeded = True
    try:
        try:
            await credential.get_token("https://storage.azure.com/.default")
            print("storage_token=OK")
        except Exception as error:
            succeeded = False
            _failure("storage_token", error)

        try:
            container = service.get_container_client(settings.metadata_snapshot_storage_container)
            await container.get_container_properties()
            print("storage_container=OK")
        except Exception as error:
            succeeded = False
            _failure("storage_container", error)

        try:
            now = datetime.now(UTC)
            await service.get_user_delegation_key(
                key_start_time=now - timedelta(minutes=5),
                key_expiry_time=now + timedelta(minutes=5),
            )
            print("storage_delegation=OK")
        except Exception as error:
            succeeded = False
            _failure("storage_delegation", error)
    finally:
        try:
            await service.close()
            await credential.close()
        except Exception as error:
            succeeded = False
            _failure("storage_close", error)
    print("storage_write=NOT_TESTED reason=read_only_diagnostic")
    return succeeded


async def run_diagnostic(tenant_id: int, *, values: Mapping[str, str] | None = None) -> int:
    """Run independent read-only checks and return a process exit code."""
    print("diagnostic_schema=1.0")
    inspection = inspect_deployment(_DEPLOYMENT_ROOT)
    print(
        f"deployment={inspection.status} files={inspection.file_count} "
        f"missing={inspection.missing_count} mismatched={inspection.mismatch_count} "
        f"unlisted_python={inspection.unlisted_python_count} "
        f"manifest_sha256={inspection.manifest_sha256 or 'unavailable'}"
        + (f" reason={inspection.reason}" if inspection.reason else "")
    )
    print(
        f"configuration_source={'OK' if inspection.configuration_matches else 'FAILED'} "
        f"actual_sha256={inspection.configuration_actual_sha256 or 'unavailable'} "
        f"expected_sha256={inspection.configuration_expected_sha256 or 'unavailable'}"
    )
    print(
        f"metadata_snapshot_source={'OK' if inspection.metadata_snapshot_matches else 'FAILED'} "
        f"actual_sha256={inspection.metadata_snapshot_actual_sha256 or 'unavailable'} "
        f"expected_sha256={inspection.metadata_snapshot_expected_sha256 or 'unavailable'}"
    )
    succeeded = inspection.status == "OK"

    source = os.environ if values is None else values
    settings, configuration_succeeded = load_settings_for_diagnostic(source)
    succeeded = succeeded and configuration_succeeded

    if settings is None:
        print("database=NOT_TESTED reason=configuration_failed")
        print("selection=NOT_TESTED reason=configuration_failed")
        print("archive=NOT_TESTED reason=configuration_failed")
        print("storage=NOT_TESTED reason=configuration_failed")
        print("storage_write=NOT_TESTED reason=read_only_diagnostic")
        print("diagnostic=FAILED")
        return 1

    database: PostgresDatabase | None = None
    selected = None
    try:
        database = PostgresDatabase(
            dsn=settings.database_dsn,
            pool_min=settings.pool_min,
            pool_max=settings.pool_max,
            pool_timeout_seconds=settings.pool_timeout_seconds,
            require_runtime_role=settings.require_https,
            expected_schema_version=settings.schema_version,
        )
        await database.open()
        readiness = await database.readiness()
        print(f"database={'OK' if readiness.ready else 'FAILED'} code={readiness.code}")
        succeeded = succeeded and readiness.ready
        try:
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                selected = await select_snapshot_datasets(
                    transaction,
                    tenant_id=tenant_id,
                    request_principal=RequestPrincipal.development(),
                    authorizer=AuthorizationService(),
                )
            print(f"selection=OK tenant_id={tenant_id} datasets={len(selected.datasets)}")
        except Exception as error:
            succeeded = False
            _failure("selection", error)
    except Exception as error:
        succeeded = False
        _failure("database", error)
        print("selection=NOT_TESTED reason=database_connection_failed")
    finally:
        if database is not None:
            try:
                await database.close()
            except Exception as error:
                succeeded = False
                _failure("database_close", error)

    if selected is None:
        print("archive=NOT_TESTED reason=selection_failed")
    else:
        try:
            now = datetime.now(UTC)
            available_until = now + timedelta(hours=settings.metadata_snapshot_retention_hours)
            with TemporaryDirectory(prefix="gds-metadata-diagnostic-") as temporary:
                archive = build_snapshot_archive(
                    Path(temporary) / "metadata.zip",
                    snapshot_id=uuid4(),
                    tenant_code=selected.tenant_code,
                    created_time=now,
                    available_until=available_until,
                    encoded_datasets=selected.datasets,
                    max_archive_bytes=settings.metadata_snapshot_max_archive_bytes,
                )
                print(f"archive=OK size_bytes={archive.size_bytes}")
        except Exception as error:
            succeeded = False
            _failure("archive", error)

    try:
        storage_succeeded = await _check_storage(settings)
    except Exception as error:
        storage_succeeded = False
        _failure("storage", error)
        print("storage_write=NOT_TESTED reason=read_only_diagnostic")
    if not storage_succeeded:
        succeeded = False
    print(f"diagnostic={'OK' if succeeded else 'FAILED'}")
    return 0 if succeeded else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=int, required=True)
    arguments = parser.parse_args()
    if arguments.tenant_id <= 0:
        parser.error("--tenant-id must be positive")
    try:
        exit_code = asyncio.run(run_diagnostic(arguments.tenant_id, values=os.environ))
    except Exception as error:
        _failure("diagnostic", error)
        print("diagnostic=FAILED")
        exit_code = 1
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
