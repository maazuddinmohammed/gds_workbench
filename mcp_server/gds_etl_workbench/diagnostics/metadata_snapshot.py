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
from typing import Any, Literal, LiteralString, cast
from uuid import uuid4

from azure.core.exceptions import AzureError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient
from psycopg import AsyncConnection
from psycopg import Error as PsycopgError
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import ConfigurationError, RuntimeSettings
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import QueryParameters, ReadTransaction
from gds_etl_workbench.tools.snapshots.archive import SnapshotContractError
from gds_etl_workbench.tools.snapshots.metadata.archive import build_snapshot_archive
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    SelectedMetadataSnapshot,
    select_snapshot_datasets,
)
from gds_etl_workbench.tools.snapshots.metadata.sql import (
    ATTRIBUTE_ROWS_SQL,
    COPY_GROUP_CONTROL_ROWS_SQL,
    COPY_GROUP_ROWS_SQL,
    COPY_ROWS_SQL,
    DISCOVERY_SCOPE_ROWS_SQL,
    FOUNDATION_CONNECTION_ROWS_SQL,
    FOUNDATION_PROJECT_ROWS_SQL,
    FOUNDATION_SYSTEM_ROWS_SQL,
    FOUNDATION_TENANT_ROWS_SQL,
    INGESTION_ATTRIBUTE_MAPPING_ROWS_SQL,
    INGESTION_OBJECT_MAPPING_ROWS_SQL,
    MEMBER_GROUP_ROWS_SQL,
    OBJECT_CLOSURE_SQL,
    OBJECT_ROWS_SQL,
    PROCESS_GROUP_ROWS_SQL,
    PROCESS_ROWS_SQL,
    REFERENCE_ROWS_SQL,
)

_CONFIGURATION_PATH = "gds_etl_workbench/configuration.py"
_METADATA_SNAPSHOT_PATH = "gds_etl_workbench/tools/snapshots/metadata/get_metadata_snapshot.py"
_SAFE_DETAIL = re.compile(r"[^A-Za-z0-9_ .,:()/'=-]")
_DEPLOYMENT_ROOT = Path(__file__).resolve().parents[2]

_RUNTIME_LOGIN = "gds_mcp_runtime"
_RUNTIME_ROLE = "gds_app_write"
_REQUIRED_SCHEMAS = ("reference", "core", "security", "model", "workflow", "mcp")
_SNAPSHOT_RELATIONS = (
    "reference.system_type",
    "reference.connection_type",
    "reference.object_type",
    "reference.zone",
    "reference.chunk_type",
    "reference.file_type",
    "reference.data_operation",
    "reference.process_type",
    "core.project",
    "core.tenant",
    "core.system",
    "core.connection",
    "core.tenant_metadata_discovery_scope",
    "core.object",
    "core.attribute",
    "core.ingestion_object_mapping",
    "core.ingestion_attribute_mapping",
    "core.copy_group",
    "core.member_group",
    "core.copy_group_control",
    "core.copy",
    "core.process_group",
    "core.process",
    "security.principal",
    "security.entra_principal_identity",
    "security.tenant_principal_access",
    "model.model",
    "model.model_scope",
)

_LOGIN_POSTURE_SQL: LiteralString = """
SELECT SESSION_USER = 'gds_mcp_runtime' AS expected_login,
       to_regrole('gds_app_write') IS NOT NULL AS role_exists,
       CASE WHEN to_regrole('gds_app_write') IS NULL THEN FALSE
            ELSE pg_has_role(SESSION_USER, 'gds_app_write', 'MEMBER')
       END AS is_member,
       CASE WHEN to_regrole('gds_app_write') IS NULL THEN FALSE
            ELSE pg_has_role(SESSION_USER, 'gds_app_write', 'SET')
       END AS can_set_role,
       EXISTS (
           SELECT 1
             FROM pg_auth_members AS membership
             JOIN pg_roles AS member_role
               ON member_role.oid = membership.member
             JOIN pg_roles AS group_role
               ON group_role.oid = membership.roleid
            WHERE member_role.rolname = SESSION_USER
              AND group_role.rolname = 'gds_app_write'
              AND NOT membership.admin_option
              AND NOT membership.inherit_option
              AND membership.set_option
       ) AS exact_membership
"""

_TRANSACTION_POSTURE_SQL: LiteralString = """
SELECT SESSION_USER = 'gds_mcp_runtime' AS expected_login,
       CURRENT_USER = 'gds_app_write' AS active_role,
       current_setting('role') = 'gds_app_write' AS local_role,
       current_setting('transaction_isolation') = 'repeatable read' AS repeatable_read,
       current_setting('transaction_read_only') = 'on' AS read_only
"""

_SCHEMA_ACL_SQL: LiteralString = """
WITH required AS (
    SELECT required_schema AS schema_name
      FROM unnest(%s::TEXT[]) AS required_schema
)
SELECT schema_name,
       namespace_record.oid IS NOT NULL AS schema_exists,
       CASE WHEN namespace_record.oid IS NULL THEN FALSE
            ELSE has_schema_privilege(CURRENT_USER, namespace_record.oid, 'USAGE')
       END AS can_use
  FROM required
  LEFT JOIN pg_namespace AS namespace_record
    ON namespace_record.nspname = required.schema_name
 ORDER BY schema_name
"""

_RELATION_ACL_SQL: LiteralString = """
WITH required AS (
    SELECT required_relation AS relation_name
      FROM unnest(%s::TEXT[]) AS required_relation
)
SELECT relation_name,
       relation_record.oid IS NOT NULL AS relation_exists,
       CASE WHEN relation_record.oid IS NULL THEN FALSE
            ELSE has_table_privilege(CURRENT_USER, relation_record.oid, 'SELECT')
       END AS can_select
  FROM required
  LEFT JOIN pg_namespace AS namespace_record
    ON namespace_record.nspname = split_part(required.relation_name, '.', 1)
  LEFT JOIN pg_class AS relation_record
    ON relation_record.relnamespace = namespace_record.oid
   AND relation_record.relname = split_part(required.relation_name, '.', 2)
 ORDER BY relation_name
"""

_READINESS_BOOTSTRAP_SQL: LiteralString = """
SELECT current_setting('server_version_num')::INTEGER / 10000 AS postgres_major,
       to_regprocedure('mcp.runtime_readiness()') IS NOT NULL AS contract_exists
"""

_READINESS_SQL: LiteralString = """
SELECT schema_version,
       postgres_major,
       schema_shape_ok,
       runtime_role_ok,
       runtime_privileges_ok,
       runtime_query_contract_ok
  FROM mcp.runtime_readiness()
"""

_SELECTION_STAGE_BY_QUERY = {
    OBJECT_CLOSURE_SQL: "object_closure",
    OBJECT_ROWS_SQL: "object_rows",
    ATTRIBUTE_ROWS_SQL: "attribute_rows",
    INGESTION_OBJECT_MAPPING_ROWS_SQL: "ingestion_object_mapping",
    INGESTION_ATTRIBUTE_MAPPING_ROWS_SQL: "ingestion_attribute_mapping",
    COPY_GROUP_ROWS_SQL: "copy_group",
    MEMBER_GROUP_ROWS_SQL: "member_group",
    COPY_GROUP_CONTROL_ROWS_SQL: "copy_group_control",
    COPY_ROWS_SQL: "copy",
    PROCESS_GROUP_ROWS_SQL: "process_group",
    PROCESS_ROWS_SQL: "process",
    DISCOVERY_SCOPE_ROWS_SQL: "discovery_scope",
    FOUNDATION_CONNECTION_ROWS_SQL: "foundation_connection",
    FOUNDATION_TENANT_ROWS_SQL: "foundation_tenant",
    FOUNDATION_PROJECT_ROWS_SQL: "foundation_project",
    FOUNDATION_SYSTEM_ROWS_SQL: "foundation_system",
    **{query: f"reference_{dataset_name}" for dataset_name, query in REFERENCE_ROWS_SQL.items()},
}


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


def _database_error_fields(error: BaseException) -> str:
    database_error = error.__cause__ if isinstance(error.__cause__, PsycopgError) else error
    if not isinstance(database_error, PsycopgError):
        return ""
    fields = ""
    if database_error is not error:
        fields = f" cause_type={type(database_error).__name__}"
    sqlstate = getattr(database_error, "sqlstate", None)
    if isinstance(sqlstate, str) and re.fullmatch(r"[A-Z0-9]{5}", sqlstate):
        fields += f" sqlstate={sqlstate}"
    return fields


def _failure_fields(error: BaseException) -> str:
    if isinstance(error, (ConfigurationError, SnapshotContractError)):
        return f"type={type(error).__name__} detail={_safe_text(error)}"
    if isinstance(error, WorkbenchError):
        return (
            f"type={type(error).__name__} code={_safe_text(error.code)}"
            f"{_database_error_fields(error)}"
        )
    if isinstance(error, AzureError):
        fields = f"type={type(error).__name__}"
        status_code = getattr(error, "status_code", None)
        error_code = getattr(error, "error_code", None)
        if isinstance(status_code, int):
            fields += f" status_code={status_code}"
        if isinstance(error_code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", error_code):
            fields += f" error_code={error_code}"
        return fields
    return f"type={type(error).__name__}{_database_error_fields(error)}"


def _failure(stage: str, error: BaseException) -> None:
    print(f"{stage}=FAILED {_failure_fields(error)}")


class _TracingReadTransaction(ReadTransaction):
    """Execute fixed selection SQL while retaining only its safe stage name."""

    def __init__(self, connection: AsyncConnection[Any]) -> None:
        self._connection = connection
        self.last_stage = "selection_start"

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: QueryParameters = (),
    ) -> dict[str, Any] | None:
        self.last_stage = _SELECTION_STAGE_BY_QUERY.get(query, "selection_unclassified")
        result = await self._connection.execute(query, parameters)
        row: dict[str, Any] | None = await result.fetchone()
        return row

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: QueryParameters = (),
    ) -> list[dict[str, Any]]:
        self.last_stage = _SELECTION_STAGE_BY_QUERY.get(query, "selection_unclassified")
        result = await self._connection.execute(query, parameters)
        rows: list[dict[str, Any]] = await result.fetchall()
        return rows


@dataclass(frozen=True, slots=True)
class _DatabaseDiagnostic:
    succeeded: bool
    selected: SelectedMetadataSnapshot | None


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


async def _run_database_diagnostic(
    settings: RuntimeSettings,
    *,
    tenant_id: int,
) -> _DatabaseDiagnostic:
    """Exercise the production pool, transaction, role, ACL, and selection path."""
    pool = AsyncConnectionPool(
        conninfo=settings.database_dsn,
        min_size=settings.pool_min,
        max_size=settings.pool_max,
        timeout=settings.pool_timeout_seconds,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
        name="gds-mcp-diagnostic",
    )
    succeeded = True
    selected: SelectedMetadataSnapshot | None = None
    try:
        try:
            await pool.open(wait=False)
        except Exception as error:
            _failure("pool_open", error)
            print("database=FAILED stage=pool_open")
            print("selection=NOT_TESTED reason=database_connection_failed")
            return _DatabaseDiagnostic(succeeded=False, selected=None)

        try:
            async with pool.connection() as connection:
                result = await connection.execute(_LOGIN_POSTURE_SQL)
                login = await result.fetchone()
            if login is None:
                print("login_posture=FAILED reason=no_result")
                succeeded = False
            else:
                login_posture = {
                    field: login[field] is True
                    for field in (
                        "expected_login",
                        "role_exists",
                        "is_member",
                        "can_set_role",
                        "exact_membership",
                    )
                }
                login_ok = all(login_posture.values())
                print(
                    f"login_posture={'OK' if login_ok else 'FAILED'} "
                    f"expected_login={login_posture['expected_login']} "
                    f"role_exists={login_posture['role_exists']} "
                    f"member={login_posture['is_member']} "
                    f"can_set_role={login_posture['can_set_role']} "
                    f"exact_membership={login_posture['exact_membership']}"
                )
                succeeded = succeeded and login_ok
        except Exception as error:
            succeeded = False
            _failure("login_posture", error)

        readiness_stage = "pool_checkout"
        readiness_row: dict[str, Any] | None = None
        readiness_reported = False
        try:
            async with pool.connection() as connection, connection.transaction():
                readiness_stage = "role_activation"
                await connection.execute("SET LOCAL ROLE gds_app_write")
                readiness_stage = "readiness_bootstrap"
                result = await connection.execute(_READINESS_BOOTSTRAP_SQL)
                bootstrap = await result.fetchone()
                if bootstrap is None:
                    print("database=FAILED code=database_posture_invalid")
                    readiness_reported = True
                    succeeded = False
                elif bootstrap["postgres_major"] != 18:
                    print("database=FAILED code=database_version_invalid")
                    readiness_reported = True
                    succeeded = False
                elif not bootstrap["contract_exists"]:
                    print("database=FAILED code=database_schema_unavailable")
                    readiness_reported = True
                    succeeded = False
                else:
                    readiness_stage = "readiness_contract"
                    result = await connection.execute(_READINESS_SQL)
                    readiness_row = await result.fetchone()
            if readiness_row is not None:
                if readiness_row["schema_version"] != settings.schema_version:
                    readiness_code = "database_schema_unavailable"
                elif readiness_row["postgres_major"] != 18:
                    readiness_code = "database_version_invalid"
                elif not readiness_row["schema_shape_ok"]:
                    readiness_code = "database_schema_unavailable"
                elif (
                    not readiness_row["runtime_role_ok"]
                    or not readiness_row["runtime_privileges_ok"]
                ):
                    readiness_code = "database_role_invalid"
                elif not readiness_row["runtime_query_contract_ok"]:
                    readiness_code = "database_schema_unavailable"
                else:
                    readiness_code = "ready"
                readiness_ok = readiness_code == "ready"
                print(f"database={'OK' if readiness_ok else 'FAILED'} code={readiness_code}")
                readiness_reported = True
                succeeded = succeeded and readiness_ok
            elif not readiness_reported:
                print("database=FAILED code=database_posture_invalid")
                succeeded = False
        except Exception as error:
            succeeded = False
            print(f"database=FAILED stage={readiness_stage} {_failure_fields(error)}")

        selection_stage = "pool_checkout"
        traced: _TracingReadTransaction | None = None
        selection_completed = False
        try:
            async with pool.connection() as connection, connection.transaction():
                selection_stage = "transaction_characteristics"
                await connection.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
                selection_stage = "role_activation"
                await connection.execute("SET LOCAL ROLE gds_app_write")
                selection_stage = "transaction_posture"
                result = await connection.execute(_TRANSACTION_POSTURE_SQL)
                transaction_posture = await result.fetchone()
                posture_fields = (
                    "expected_login",
                    "active_role",
                    "local_role",
                    "repeatable_read",
                    "read_only",
                )
                safe_posture = (
                    None
                    if transaction_posture is None
                    else {field: transaction_posture[field] is True for field in posture_fields}
                )
                transaction_ok = safe_posture is not None and all(safe_posture.values())
                if transaction_posture is None:
                    print("transaction_posture=FAILED reason=no_result")
                else:
                    assert safe_posture is not None
                    print(
                        f"transaction_posture={'OK' if transaction_ok else 'FAILED'} "
                        f"expected_login={safe_posture['expected_login']} "
                        f"active_role={safe_posture['active_role']} "
                        f"local_role={safe_posture['local_role']} "
                        f"repeatable_read={safe_posture['repeatable_read']} "
                        f"read_only={safe_posture['read_only']}"
                    )
                succeeded = succeeded and transaction_ok

                selection_stage = "schema_acl"
                result = await connection.execute(_SCHEMA_ACL_SQL, (list(_REQUIRED_SCHEMAS),))
                schema_acl = await result.fetchall()
                schema_access = {
                    row["schema_name"]: (
                        row["schema_exists"] is True,
                        row["can_use"] is True,
                    )
                    for row in schema_acl
                    if row.get("schema_name") in _REQUIRED_SCHEMAS
                }
                missing_schemas = [
                    name
                    for name in _REQUIRED_SCHEMAS
                    if schema_access.get(name, (False, False))[0] is not True
                ]
                unreadable_schemas = [
                    name
                    for name in _REQUIRED_SCHEMAS
                    if schema_access.get(name, (False, False))[0] is True
                    and schema_access[name][1] is not True
                ]

                selection_stage = "relation_acl"
                result = await connection.execute(
                    _RELATION_ACL_SQL,
                    (list(_SNAPSHOT_RELATIONS),),
                )
                relation_acl = await result.fetchall()
                relation_access = {
                    row["relation_name"]: (
                        row["relation_exists"] is True,
                        row["can_select"] is True,
                    )
                    for row in relation_acl
                    if row.get("relation_name") in _SNAPSHOT_RELATIONS
                }
                missing_relations = [
                    name
                    for name in _SNAPSHOT_RELATIONS
                    if relation_access.get(name, (False, False))[0] is not True
                ]
                unreadable_relations = [
                    name
                    for name in _SNAPSHOT_RELATIONS
                    if relation_access.get(name, (False, False))[0] is True
                    and relation_access[name][1] is not True
                ]
                acl_ok = (
                    not missing_schemas
                    and not unreadable_schemas
                    and not missing_relations
                    and not unreadable_relations
                )
                print(
                    f"snapshot_acl={'OK' if acl_ok else 'FAILED'} "
                    f"schemas_missing={','.join(missing_schemas) or 'none'} "
                    f"schema_usage_missing={','.join(unreadable_schemas) or 'none'} "
                    f"relations_missing={','.join(missing_relations) or 'none'} "
                    f"select_missing={','.join(unreadable_relations) or 'none'}"
                )
                succeeded = succeeded and acl_ok

                traced = _TracingReadTransaction(connection)
                selection_stage = "selection_start"
                selected = await select_snapshot_datasets(
                    traced,
                    tenant_id=tenant_id,
                    request_principal=RequestPrincipal.development(),
                    authorizer=AuthorizationService(),
                )
                selection_completed = True
                selection_stage = "transaction_commit"
            print(f"selection=OK tenant_id={tenant_id} datasets={len(selected.datasets)}")
        except Exception as error:
            succeeded = False
            database_error = error.__cause__ if isinstance(error.__cause__, PsycopgError) else error
            if (
                isinstance(database_error, PsycopgError)
                and traced is not None
                and not selection_completed
            ):
                selection_stage = traced.last_stage
            elif not isinstance(database_error, PsycopgError):
                selection_stage = "selection_contract"
            print(f"selection=FAILED stage={selection_stage} {_failure_fields(error)}")

    finally:
        try:
            await pool.close()
        except Exception as error:
            succeeded = False
            _failure("pool_close", error)
    return _DatabaseDiagnostic(succeeded=succeeded, selected=selected)


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
    print("diagnostic_schema=2.0")
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

    print(
        f"environment={settings.environment.value} runtime_role_required=True "
        f"runtime_login={_RUNTIME_LOGIN} runtime_role={_RUNTIME_ROLE}"
    )
    database_diagnostic = await _run_database_diagnostic(settings, tenant_id=tenant_id)
    succeeded = succeeded and database_diagnostic.succeeded
    selected = database_diagnostic.selected

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
