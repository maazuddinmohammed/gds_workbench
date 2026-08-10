"""Environment-only runtime configuration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from os import environ

from psycopg.conninfo import conninfo_to_dict


class ConfigurationError(ValueError):
    """A safe configuration failure that never includes secret values."""


class Environment(StrEnum):
    LOCAL = "local"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    DEV = "dev"
    AZURE_EASY_AUTH = "azure_easy_auth"


_EXPECTED_KEYS = frozenset(
    {
        "GDS_AUTH_MODE",
        "GDS_CURSOR_SIGNING_KEY",
        "GDS_DATABASE_CONNECTION_BUDGET",
        "GDS_DATABASE_CONNECTION_HEADROOM",
        "GDS_DATABASE_DSN",
        "GDS_DATABASE_POOL_MAX",
        "GDS_DATABASE_POOL_MIN",
        "GDS_DATABASE_POOL_TIMEOUT_SECONDS",
        "GDS_ENVIRONMENT",
        "GDS_MCP_ALLOWED_HOSTS",
        "GDS_REQUEST_TIMEOUT_SECONDS",
        "GDS_REQUIRE_HTTPS",
        "GDS_SCHEMA_VERSION",
        "PORT",
        "WEB_CONCURRENCY",
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
    require_https: bool
    schema_version: str
    port: int
    web_concurrency: int
    pool_min: int
    pool_max: int
    pool_timeout_seconds: int
    database_connection_budget: int
    database_connection_headroom: int
    request_timeout_seconds: int

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> RuntimeSettings:
        source = environ if values is None else values
        unknown = sorted(
            key for key in source if key.startswith("GDS_") and key not in _EXPECTED_KEYS
        )
        if unknown:
            raise ConfigurationError(f"unsupported GDS setting: {unknown[0]}")

        environment = _enum_value(source, "GDS_ENVIRONMENT", Environment)
        auth_mode = _enum_value(source, "GDS_AUTH_MODE", AuthMode)
        if environment is Environment.PRODUCTION and auth_mode is not AuthMode.AZURE_EASY_AUTH:
            raise ConfigurationError("production requires GDS_AUTH_MODE=azure_easy_auth")
        if auth_mode is AuthMode.DEV and environment is not Environment.LOCAL:
            raise ConfigurationError("GDS_AUTH_MODE=dev requires GDS_ENVIRONMENT=local")

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

        require_https = _boolean(source, "GDS_REQUIRE_HTTPS")
        if environment is Environment.PRODUCTION and not require_https:
            raise ConfigurationError("production requires GDS_REQUIRE_HTTPS=true")

        allowed_hosts = tuple(
            part.strip()
            for part in _required(source, "GDS_MCP_ALLOWED_HOSTS").split(",")
            if part.strip()
        )
        if not allowed_hosts or any(host == "*" for host in allowed_hosts):
            raise ConfigurationError("GDS_MCP_ALLOWED_HOSTS requires an explicit host allowlist")

        schema_version = _required(source, "GDS_SCHEMA_VERSION")
        if schema_version != "1.0.0":
            raise ConfigurationError("GDS_SCHEMA_VERSION must be 1.0.0")

        port = _integer(source, "PORT", minimum=1, maximum=65535)
        web_concurrency = _integer(source, "WEB_CONCURRENCY", minimum=1, maximum=32)
        pool_min = _integer(source, "GDS_DATABASE_POOL_MIN", minimum=1, maximum=100)
        pool_max = _integer(source, "GDS_DATABASE_POOL_MAX", minimum=1, maximum=100)
        pool_timeout = _integer(source, "GDS_DATABASE_POOL_TIMEOUT_SECONDS", minimum=1, maximum=120)
        connection_budget = _integer(
            source, "GDS_DATABASE_CONNECTION_BUDGET", minimum=2, maximum=10000
        )
        connection_headroom = _integer(
            source, "GDS_DATABASE_CONNECTION_HEADROOM", minimum=1, maximum=9999
        )
        request_timeout = _integer(source, "GDS_REQUEST_TIMEOUT_SECONDS", minimum=1, maximum=600)

        if pool_min > pool_max:
            raise ConfigurationError("database pool minimum cannot exceed maximum")
        if connection_headroom >= connection_budget:
            raise ConfigurationError("database connection headroom must be below budget")
        if web_concurrency * pool_max > connection_budget - connection_headroom:
            raise ConfigurationError(
                "worker and pool settings exceed the database connection budget"
            )

        return cls(
            environment=environment,
            auth_mode=auth_mode,
            database_dsn=database_dsn,
            cursor_signing_key=cursor_signing_key,
            allowed_hosts=allowed_hosts,
            require_https=require_https,
            schema_version=schema_version,
            port=port,
            web_concurrency=web_concurrency,
            pool_min=pool_min,
            pool_max=pool_max,
            pool_timeout_seconds=pool_timeout,
            database_connection_budget=connection_budget,
            database_connection_headroom=connection_headroom,
            request_timeout_seconds=request_timeout,
        )


def _required(source: Mapping[str, str], key: str) -> str:
    value = source.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"{key} is required")
    return value


def _integer(source: Mapping[str, str], key: str, *, minimum: int, maximum: int) -> int:
    raw = _required(source, key)
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{key} must be between {minimum} and {maximum}")
    return value


def _boolean(source: Mapping[str, str], key: str) -> bool:
    raw = _required(source, key).lower()
    if raw not in {"true", "false"}:
        raise ConfigurationError(f"{key} must be true or false")
    return raw == "true"


def _enum_value[
    EnumT: StrEnum,
](source: Mapping[str, str], key: str, enum_type: type[EnumT]) -> EnumT:
    raw = _required(source, key)
    try:
        return enum_type(raw)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ConfigurationError(f"{key} must be one of: {allowed}") from exc
