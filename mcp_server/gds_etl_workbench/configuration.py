"""Deployment configuration and checked-in runtime policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from os import environ
from re import fullmatch
from urllib.parse import urlsplit
from uuid import UUID

from psycopg.conninfo import conninfo_to_dict


class ConfigurationError(ValueError):
    """A safe configuration failure that never includes secret values."""


class Environment(StrEnum):
    LOCAL = "local"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    DEV = "dev"
    AZURE_EASY_AUTH = "azure_easy_auth"


SCHEMA_VERSION = "1.0.0"
SNAPSHOT_DOWNLOAD_TTL_SECONDS = 900
SNAPSHOT_RETENTION_HOURS = 24
SNAPSHOT_MAX_ARCHIVE_BYTES = 268_435_456
DATABASE_POOL_MIN = 1
DATABASE_POOL_MAX = 5
DATABASE_POOL_TIMEOUT_SECONDS = 10
DATABASE_CONNECTION_BUDGET = 100
DATABASE_CONNECTION_HEADROOM = 20
WEB_CONCURRENCY = 2


_EXPECTED_KEYS = frozenset(
    {
        "GDS_CURSOR_SIGNING_KEY",
        "GDS_DATABASE_DSN",
        "GDS_ENTRA_API_CLIENT_ID",
        "GDS_ENTRA_TENANT_ID",
        "GDS_ENVIRONMENT",
        "GDS_MCP_PUBLIC_URL",
        "GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID",
        "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL",
        "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Validated process settings. Secret-bearing fields are excluded from repr."""

    environment: Environment
    auth_mode: AuthMode
    database_dsn: str = field(repr=False)
    cursor_signing_key: bytes = field(repr=False)
    allowed_hosts: tuple[str, ...]
    mcp_public_url: str
    entra_tenant_id: UUID
    entra_api_client_id: UUID
    require_https: bool
    schema_version: str
    pool_min: int
    pool_max: int
    pool_timeout_seconds: int
    metadata_snapshot_storage_account_url: str
    metadata_snapshot_storage_container: str
    metadata_snapshot_download_ttl_seconds: int
    metadata_snapshot_retention_hours: int
    metadata_snapshot_max_archive_bytes: int
    metadata_snapshot_managed_identity_client_id: UUID | None

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> RuntimeSettings:
        source = environ if values is None else values
        unknown = sorted(
            key for key in source if key.startswith("GDS_") and key not in _EXPECTED_KEYS
        )
        if unknown:
            raise ConfigurationError(f"unsupported GDS setting: {unknown[0]}")

        environment = _enum_value(source, "GDS_ENVIRONMENT", Environment)
        auth_mode = AuthMode.DEV if environment is Environment.LOCAL else AuthMode.AZURE_EASY_AUTH

        database_dsn = _required(source, "GDS_DATABASE_DSN")
        if environment is Environment.PRODUCTION:
            try:
                dsn_parts = conninfo_to_dict(database_dsn)
            except Exception as exc:
                raise ConfigurationError("GDS_DATABASE_DSN is invalid") from exc
            if not dsn_parts.get("host") or not dsn_parts.get("dbname"):
                raise ConfigurationError("production database DSN requires host and dbname")
            if dsn_parts.get("sslmode") != "verify-full":
                raise ConfigurationError("production database DSN requires sslmode=verify-full")

        cursor_signing_key = _required(source, "GDS_CURSOR_SIGNING_KEY").encode("utf-8")
        if not 32 <= len(cursor_signing_key) <= 4096:
            raise ConfigurationError("GDS_CURSOR_SIGNING_KEY must be 32-4096 UTF-8 bytes")

        require_https = environment is Environment.PRODUCTION

        mcp_public_url = _required(source, "GDS_MCP_PUBLIC_URL")
        parsed_mcp_url = urlsplit(mcp_public_url)
        try:
            mcp_port = parsed_mcp_url.port
        except ValueError as exc:
            raise ConfigurationError("GDS_MCP_PUBLIC_URL is invalid") from exc
        if (
            parsed_mcp_url.scheme not in {"http", "https"}
            or not parsed_mcp_url.hostname
            or parsed_mcp_url.username is not None
            or parsed_mcp_url.password is not None
            or parsed_mcp_url.path != "/mcp"
            or parsed_mcp_url.query
            or parsed_mcp_url.fragment
            or (parsed_mcp_url.scheme == "https" and mcp_port == 80)
            or (parsed_mcp_url.scheme == "http" and mcp_port == 443)
        ):
            raise ConfigurationError("GDS_MCP_PUBLIC_URL must be an absolute HTTP(S) /mcp endpoint")
        if environment is Environment.PRODUCTION and parsed_mcp_url.scheme != "https":
            raise ConfigurationError("production GDS_MCP_PUBLIC_URL must use HTTPS")

        public_host = parsed_mcp_url.hostname
        if ":" in public_host:
            public_host = f"[{public_host}]"
        allowed_hosts = [public_host, f"{public_host}:*"]
        if environment is Environment.LOCAL:
            allowed_hosts.extend(
                [
                    "localhost",
                    "localhost:*",
                    "127.0.0.1",
                    "127.0.0.1:*",
                    "[::1]",
                    "[::1]:*",
                ]
            )
        allowed_hosts = tuple(dict.fromkeys(allowed_hosts))

        try:
            entra_tenant_id = UUID(_required(source, "GDS_ENTRA_TENANT_ID"))
        except ValueError as exc:
            raise ConfigurationError("GDS_ENTRA_TENANT_ID must be a UUID") from exc
        if entra_tenant_id.int == 0:
            raise ConfigurationError("GDS_ENTRA_TENANT_ID must be a nonzero UUID")

        try:
            entra_api_client_id = UUID(_required(source, "GDS_ENTRA_API_CLIENT_ID"))
        except ValueError as exc:
            raise ConfigurationError("GDS_ENTRA_API_CLIENT_ID must be a UUID") from exc
        if entra_api_client_id.int == 0:
            raise ConfigurationError("GDS_ENTRA_API_CLIENT_ID must be a nonzero UUID")

        account_url = _required(source, "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL")
        parsed_account_url = urlsplit(account_url)
        try:
            account_port = parsed_account_url.port
        except ValueError as exc:
            raise ConfigurationError(
                "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL is invalid"
            ) from exc
        if (
            parsed_account_url.scheme != "https"
            or not parsed_account_url.hostname
            or parsed_account_url.username is not None
            or parsed_account_url.password is not None
            or account_port is not None
            or parsed_account_url.path not in {"", "/"}
            or parsed_account_url.query
            or parsed_account_url.fragment
        ):
            raise ConfigurationError(
                "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL must be an HTTPS account root"
            )
        account_url = account_url.rstrip("/")

        storage_container = _required(
            source,
            "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER",
        )
        if (
            fullmatch(
                r"(?!.*--)[a-z0-9][a-z0-9-]{1,61}[a-z0-9]",
                storage_container,
            )
            is None
        ):
            raise ConfigurationError(
                "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER must be a valid container name"
            )

        client_id_text = source.get(
            "GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID",
            "",
        ).strip()
        try:
            managed_identity_client_id = UUID(client_id_text) if client_id_text else None
        except ValueError as exc:
            raise ConfigurationError(
                "GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID must be a UUID"
            ) from exc

        if DATABASE_POOL_MIN > DATABASE_POOL_MAX:
            raise ConfigurationError("database pool minimum cannot exceed maximum")
        if DATABASE_CONNECTION_HEADROOM >= DATABASE_CONNECTION_BUDGET:
            raise ConfigurationError("database connection headroom must be below budget")
        if WEB_CONCURRENCY * DATABASE_POOL_MAX > (
            DATABASE_CONNECTION_BUDGET - DATABASE_CONNECTION_HEADROOM
        ):
            raise ConfigurationError(
                "worker and pool settings exceed the database connection budget"
            )

        return cls(
            environment=environment,
            auth_mode=auth_mode,
            database_dsn=database_dsn,
            cursor_signing_key=cursor_signing_key,
            allowed_hosts=allowed_hosts,
            mcp_public_url=mcp_public_url,
            entra_tenant_id=entra_tenant_id,
            entra_api_client_id=entra_api_client_id,
            require_https=require_https,
            schema_version=SCHEMA_VERSION,
            pool_min=DATABASE_POOL_MIN,
            pool_max=DATABASE_POOL_MAX,
            pool_timeout_seconds=DATABASE_POOL_TIMEOUT_SECONDS,
            metadata_snapshot_storage_account_url=account_url,
            metadata_snapshot_storage_container=storage_container,
            metadata_snapshot_download_ttl_seconds=SNAPSHOT_DOWNLOAD_TTL_SECONDS,
            metadata_snapshot_retention_hours=SNAPSHOT_RETENTION_HOURS,
            metadata_snapshot_max_archive_bytes=SNAPSHOT_MAX_ARCHIVE_BYTES,
            metadata_snapshot_managed_identity_client_id=managed_identity_client_id,
        )


def _required(source: Mapping[str, str], key: str) -> str:
    value = source.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"{key} is required")
    return value


def _enum_value[
    EnumT: StrEnum,
](source: Mapping[str, str], key: str, enum_type: type[EnumT]) -> EnumT:
    raw = _required(source, key)
    try:
        return enum_type(raw)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ConfigurationError(f"{key} must be one of: {allowed}") from exc
