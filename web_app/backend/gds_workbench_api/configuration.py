"""Validated web-backend deployment configuration."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from os import environ
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit
from uuid import UUID

from gds_etl_workbench.configuration import (
    DATABASE_POOL_MAX,
    DATABASE_POOL_MIN,
    DATABASE_POOL_TIMEOUT_SECONDS,
    ConfigurationError,
    Environment,
)
from psycopg.conninfo import conninfo_to_dict

from gds_workbench_api.features.workflows.execution.configuration import (
    WorkflowExecutionConfiguration,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentRuntimeConfiguration,
)

_EXPECTED_KEYS = frozenset(
    {
        "GDS_WEB_DATABASE_DSN",
        "GDS_WEB_AGENT_EXECUTION_MODE",
        "GDS_WEB_AGENT_TIMEOUT_SECONDS",
        "GDS_WEB_CURSOR_SIGNING_KEY",
        "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE",
        "GDS_WEB_DATABRICKS_EXECUTION_MODE",
        "GDS_WEB_DATABRICKS_MODEL_ENDPOINT",
        "GDS_WEB_ENVIRONMENT",
        "GDS_WEB_ENTRA_TENANT_ID",
        "GDS_WEB_LOCAL_ENTRA_TENANT_ID",
        "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID",
        "GDS_WEB_STATIC_DIR",
        "GDS_WEB_WORKFLOW_ERROR_POLL_SECONDS",
        "GDS_WEB_WORKFLOW_HEARTBEAT_SECONDS",
        "GDS_WEB_WORKFLOW_IDLE_POLL_SECONDS",
        "GDS_WEB_WORKFLOW_LEASE_SECONDS",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    environment: Environment
    database_dsn: str = field(repr=False)
    cursor_signing_key: bytes = field(repr=False)
    databricks_environment_code: str
    databricks_execution_mode: Literal["fake", "remote"]
    agent_runtime: AgentRuntimeConfiguration = field(repr=False)
    workflow_execution: WorkflowExecutionConfiguration
    static_directory: Path | None
    entra_tenant_id: UUID
    local_principal_object_id: UUID | None
    databricks_host: str | None
    databricks_app_name: str | None
    databricks_workspace_id: int | None
    pool_min: int = DATABASE_POOL_MIN
    pool_max: int = DATABASE_POOL_MAX
    pool_timeout_seconds: int = DATABASE_POOL_TIMEOUT_SECONDS

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> RuntimeSettings:
        source = environ if values is None else values
        unknown = sorted(
            key for key in source if key.startswith("GDS_WEB_") and key not in _EXPECTED_KEYS
        )
        if unknown:
            raise ConfigurationError(f"unsupported GDS web setting: {unknown[0]}")

        try:
            environment = Environment(_required(source, "GDS_WEB_ENVIRONMENT"))
        except ValueError as exc:
            raise ConfigurationError("GDS_WEB_ENVIRONMENT must be local or production") from exc

        raw_static_directory = source.get("GDS_WEB_STATIC_DIR", "").strip()
        if environment is Environment.PRODUCTION and not raw_static_directory:
            raise ConfigurationError("GDS_WEB_STATIC_DIR is required in production")
        static_directory = Path(raw_static_directory) if raw_static_directory else None

        local_tenant = _optional_uuid(source, "GDS_WEB_LOCAL_ENTRA_TENANT_ID")
        local_principal = _optional_uuid(source, "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID")
        production_tenant = _optional_uuid(source, "GDS_WEB_ENTRA_TENANT_ID")
        if environment is Environment.LOCAL and (local_tenant is None or local_principal is None):
            raise ConfigurationError(
                "local web mode requires explicit Entra Tenant and Principal Object IDs"
            )
        if environment is Environment.PRODUCTION and (
            local_tenant is not None or local_principal is not None
        ):
            raise ConfigurationError("local web identity settings are not allowed in production")
        if environment is Environment.LOCAL and production_tenant is not None:
            raise ConfigurationError("production web identity settings are not allowed locally")
        if environment is Environment.PRODUCTION and production_tenant is None:
            raise ConfigurationError("GDS_WEB_ENTRA_TENANT_ID is required in production")
        entra_tenant_id = local_tenant if environment is Environment.LOCAL else production_tenant
        if entra_tenant_id is None:
            raise ConfigurationError("the web Entra Tenant ID is unavailable")

        database_dsn = _required(source, "GDS_WEB_DATABASE_DSN")
        if environment is Environment.PRODUCTION:
            try:
                dsn_parts = conninfo_to_dict(database_dsn)
            except Exception as exc:
                raise ConfigurationError("GDS_WEB_DATABASE_DSN is invalid") from exc
            if not dsn_parts.get("host") or not dsn_parts.get("dbname"):
                raise ConfigurationError("production database DSN requires host and dbname")
            if dsn_parts.get("sslmode") != "verify-full":
                raise ConfigurationError("production database DSN requires sslmode=verify-full")

        cursor_signing_key = _required(source, "GDS_WEB_CURSOR_SIGNING_KEY").encode()
        if not 32 <= len(cursor_signing_key) <= 4096:
            raise ConfigurationError("GDS_WEB_CURSOR_SIGNING_KEY must be 32-4096 UTF-8 bytes")
        databricks_environment_code = _required(
            source,
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE",
        )
        if (
            re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_.-]{0,99}",
                databricks_environment_code,
            )
            is None
        ):
            raise ConfigurationError(
                "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE must be a bounded Environment code"
            )
        raw_databricks_mode = source.get(
            "GDS_WEB_DATABRICKS_EXECUTION_MODE",
            "remote" if environment is Environment.PRODUCTION else "fake",
        ).strip()
        if raw_databricks_mode not in {"fake", "remote"}:
            raise ConfigurationError("GDS_WEB_DATABRICKS_EXECUTION_MODE must be fake or remote")
        if environment is Environment.PRODUCTION and raw_databricks_mode == "fake":
            raise ConfigurationError("fake Databricks execution is available only locally")

        databricks_host: str | None = None
        databricks_app_name: str | None = None
        databricks_workspace_id: int | None = None
        if environment is Environment.PRODUCTION:
            databricks_host = _https_origin(
                _required(source, "DATABRICKS_HOST"),
                setting="DATABRICKS_HOST",
            )
            databricks_app_name = _required(source, "DATABRICKS_APP_NAME")
            if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", databricks_app_name) is None:
                raise ConfigurationError("DATABRICKS_APP_NAME is invalid")
            raw_workspace_id = _required(source, "DATABRICKS_WORKSPACE_ID")
            try:
                databricks_workspace_id = int(raw_workspace_id)
            except ValueError as exc:
                raise ConfigurationError("DATABRICKS_WORKSPACE_ID must be an integer") from exc
            if databricks_workspace_id <= 0:
                raise ConfigurationError("DATABRICKS_WORKSPACE_ID must be positive")

        return cls(
            environment=environment,
            database_dsn=database_dsn,
            cursor_signing_key=cursor_signing_key,
            databricks_environment_code=databricks_environment_code,
            databricks_execution_mode=cast(Literal["fake", "remote"], raw_databricks_mode),
            agent_runtime=AgentRuntimeConfiguration.from_environment(
                source,
                production=environment is Environment.PRODUCTION,
            ),
            workflow_execution=WorkflowExecutionConfiguration.from_environment(source),
            static_directory=static_directory,
            entra_tenant_id=entra_tenant_id,
            local_principal_object_id=local_principal,
            databricks_host=databricks_host,
            databricks_app_name=databricks_app_name,
            databricks_workspace_id=databricks_workspace_id,
        )


def _required(source: Mapping[str, str], key: str) -> str:
    value = source.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"{key} is required")
    return value


def _optional_uuid(source: Mapping[str, str], key: str) -> UUID | None:
    value = source.get(key, "").strip()
    if not value:
        return None
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be a UUID") from exc
    if parsed.int == 0:
        raise ConfigurationError(f"{key} must be a nonzero UUID")
    return parsed


def _https_origin(value: str, *, setting: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(f"{setting} must be a valid HTTPS origin")
    return value.rstrip("/")
