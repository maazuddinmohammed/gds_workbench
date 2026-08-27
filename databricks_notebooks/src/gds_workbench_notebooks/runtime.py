"""Source-only Databricks notebook bootstrap and PostgreSQL configuration."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .errors import (
    NotebookAuthorizationError,
    NotebookConfigurationError,
    NotebookDatabaseError,
)

_ENV_FILE_MAX_BYTES = 64 * 1024
_ALLOWED_ENV_KEYS = frozenset(
    {
        "GDS_NOTEBOOK_POSTGRES_HOST",
        "GDS_NOTEBOOK_POSTGRES_PORT",
        "GDS_NOTEBOOK_POSTGRES_DATABASE",
        "GDS_NOTEBOOK_POSTGRES_USER",
        "GDS_NOTEBOOK_POSTGRES_PASSWORD",
        "GDS_NOTEBOOK_POSTGRES_SSLMODE",
        "GDS_NOTEBOOK_POSTGRES_CONNECT_TIMEOUT_SECONDS",
        "GDS_NOTEBOOK_POSTGRES_STATEMENT_TIMEOUT_SECONDS",
        "GDS_NOTEBOOK_WORKFLOW_LEASE_SECONDS",
        "GDS_NOTEBOOK_WORKFLOW_HEARTBEAT_SECONDS",
        "GDS_NOTEBOOK_AGENT_TIMEOUT_SECONDS",
        "GDS_NOTEBOOK_DATABRICKS_MODEL_ENDPOINT",
    }
)
_REQUIRED_ENV_KEYS = frozenset(
    {
        "GDS_NOTEBOOK_POSTGRES_HOST",
        "GDS_NOTEBOOK_POSTGRES_PORT",
        "GDS_NOTEBOOK_POSTGRES_DATABASE",
        "GDS_NOTEBOOK_POSTGRES_USER",
        "GDS_NOTEBOOK_POSTGRES_PASSWORD",
    }
)


@dataclass(frozen=True, slots=True)
class NotebookDatabaseSettings:
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    sslmode: str = "require"
    connect_timeout_seconds: int = 10
    statement_timeout_seconds: int = 30


@dataclass(frozen=True, slots=True)
class NotebookRuntimeSettings:
    database: NotebookDatabaseSettings
    workflow_lease_seconds: int = 30
    workflow_heartbeat_seconds: int = 10
    agent_timeout_seconds: int = 120
    databricks_model_endpoint: str | None = None


def locate_uploaded_root(start: Path) -> Path:
    """Find the uploaded root from the notebook directory or a descendant."""
    try:
        candidate = start.expanduser().resolve(strict=False)
    except OSError:
        raise NotebookConfigurationError(
            "The uploaded notebook root could not be resolved."
        ) from None
    if candidate.is_file():
        candidate = candidate.parent

    for directory in (candidate, *candidate.parents):
        if (
            (directory / "src" / "gds_workbench_notebooks" / "__init__.py").is_file()
            and (directory / "notebooks").is_dir()
            and (directory / "requirements.txt").is_file()
        ):
            return directory
    raise NotebookConfigurationError(
        "The uploaded notebook root must contain src, notebooks, and requirements.txt."
    )


def load_notebook_database_settings(uploaded_root: Path) -> NotebookDatabaseSettings:
    """Load the strict root .env without copying values into process environment."""
    values = _load_notebook_env(uploaded_root)
    return _database_settings(values)


def load_notebook_runtime_settings(uploaded_root: Path) -> NotebookRuntimeSettings:
    """Load validated database and bounded Workflow runtime settings."""
    values = _load_notebook_env(uploaded_root)
    lease_seconds = _bounded_integer(
        values.get("GDS_NOTEBOOK_WORKFLOW_LEASE_SECONDS", "30"),
        label="Workflow lease duration",
        minimum=1,
        maximum=300,
    )
    heartbeat_seconds = _bounded_integer(
        values.get("GDS_NOTEBOOK_WORKFLOW_HEARTBEAT_SECONDS", "10"),
        label="Workflow heartbeat interval",
        minimum=1,
        maximum=299,
    )
    if heartbeat_seconds >= lease_seconds:
        raise NotebookConfigurationError(
            "Workflow heartbeat interval must be shorter than the lease duration."
        )
    agent_timeout_seconds = _bounded_integer(
        values.get("GDS_NOTEBOOK_AGENT_TIMEOUT_SECONDS", "120"),
        label="Agent timeout",
        minimum=1,
        maximum=600,
    )
    endpoint = values.get("GDS_NOTEBOOK_DATABRICKS_MODEL_ENDPOINT", "").strip()
    if endpoint == "<serving-endpoint-name>":
        endpoint = ""
    if endpoint and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", endpoint) is None:
        raise NotebookConfigurationError(
            "Databricks model endpoint must be a valid serving endpoint name."
        )
    return NotebookRuntimeSettings(
        database=_database_settings(values),
        workflow_lease_seconds=lease_seconds,
        workflow_heartbeat_seconds=heartbeat_seconds,
        agent_timeout_seconds=agent_timeout_seconds,
        databricks_model_endpoint=endpoint or None,
    )


def _load_notebook_env(uploaded_root: Path) -> dict[str, str]:
    env_path = uploaded_root / ".env"
    try:
        if not env_path.is_file() or env_path.stat().st_size > _ENV_FILE_MAX_BYTES:
            raise NotebookConfigurationError(
                "Create a bounded .env file in the uploaded notebook root."
            )
        document = env_path.read_text(encoding="utf-8")
    except NotebookConfigurationError:
        raise
    except (OSError, UnicodeError):
        raise NotebookConfigurationError(
            "The uploaded notebook .env file could not be read."
        ) from None

    values = _parse_env_document(document)
    unexpected = sorted(set(values) - _ALLOWED_ENV_KEYS)
    if unexpected:
        raise NotebookConfigurationError(
            f"The notebook .env contains an unsupported field: {unexpected[0]}."
        )
    missing = sorted(key for key in _REQUIRED_ENV_KEYS if not values.get(key, ""))
    if missing:
        raise NotebookConfigurationError(
            f"The notebook .env is missing a required field: {missing[0]}."
        )
    return values


def _database_settings(values: dict[str, str]) -> NotebookDatabaseSettings:
    host = _validate_host(values["GDS_NOTEBOOK_POSTGRES_HOST"])
    database = _validate_connection_text(
        values["GDS_NOTEBOOK_POSTGRES_DATABASE"],
        label="PostgreSQL database",
        maximum=255,
    )
    user = _validate_connection_text(
        values["GDS_NOTEBOOK_POSTGRES_USER"],
        label="PostgreSQL user",
        maximum=255,
    )
    if user != "gds_notebook_runtime":
        raise NotebookConfigurationError(
            "PostgreSQL user must be the provisioned gds_notebook_runtime login."
        )
    password = _validate_password(values["GDS_NOTEBOOK_POSTGRES_PASSWORD"])
    port = _bounded_integer(
        values["GDS_NOTEBOOK_POSTGRES_PORT"],
        label="PostgreSQL port",
        minimum=1,
        maximum=65_535,
    )
    sslmode = values.get("GDS_NOTEBOOK_POSTGRES_SSLMODE", "require")
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise NotebookConfigurationError(
            "PostgreSQL SSL mode must be require, verify-ca, or verify-full."
        )
    connect_timeout = _bounded_integer(
        values.get("GDS_NOTEBOOK_POSTGRES_CONNECT_TIMEOUT_SECONDS", "10"),
        label="PostgreSQL connect timeout",
        minimum=1,
        maximum=60,
    )
    statement_timeout = _bounded_integer(
        values.get("GDS_NOTEBOOK_POSTGRES_STATEMENT_TIMEOUT_SECONDS", "30"),
        label="PostgreSQL statement timeout",
        minimum=1,
        maximum=300,
    )
    return NotebookDatabaseSettings(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        sslmode=sslmode,
        connect_timeout_seconds=connect_timeout,
        statement_timeout_seconds=statement_timeout,
    )


@contextmanager
def notebook_database_connection(
    settings: NotebookDatabaseSettings,
    *,
    connector: Callable[..., Any] = psycopg.connect,
) -> Iterator[Any]:
    """Open one explicit connection while keeping its password out of output."""
    try:
        connection = connector(
            host=settings.host,
            port=settings.port,
            dbname=settings.database,
            user=settings.user,
            password=settings.password,
            sslmode=settings.sslmode,
            connect_timeout=settings.connect_timeout_seconds,
            application_name="gds_workbench_databricks_notebook",
            options=(f"-c statement_timeout={settings.statement_timeout_seconds * 1000}"),
            row_factory=dict_row,
        )
        with connection:
            yield connection
    except (NotebookAuthorizationError, NotebookConfigurationError, NotebookDatabaseError):
        raise
    except Exception:
        raise NotebookDatabaseError(
            "The notebook PostgreSQL operation failed. Verify connection settings "
            "and notebook database provisioning."
        ) from None


def _parse_env_document(document: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(document.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
        if match is None:
            raise NotebookConfigurationError(
                f"The notebook .env has invalid syntax on line {line_number}."
            )
        key, raw_value = match.groups()
        if key in values:
            raise NotebookConfigurationError(f"The notebook .env repeats field {key}.")
        value = raw_value.strip()
        if value[:1] in {"'", '"'}:
            quote = value[0]
            if len(value) < 2 or value[-1] != quote:
                raise NotebookConfigurationError(
                    f"The notebook .env has invalid quoting on line {line_number}."
                )
            value = value[1:-1]
        if "\x00" in value or "\r" in value or "\n" in value:
            raise NotebookConfigurationError(
                f"The notebook .env has an invalid value on line {line_number}."
            )
        values[key] = value
    return values


def _validate_host(value: str) -> str:
    host = value.strip()
    _reject_placeholder(host, label="PostgreSQL host")
    if len(host) > 253:
        raise NotebookConfigurationError("PostgreSQL host is invalid.")
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    labels = host.removesuffix(".").split(".")
    if not labels or any(
        len(label) > 63 or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label) is None
        for label in labels
    ):
        raise NotebookConfigurationError("PostgreSQL host is invalid.")
    return host


def _validate_connection_text(value: str, *, label: str, maximum: int) -> str:
    normalized = value.strip()
    _reject_placeholder(normalized, label=label)
    if (
        not normalized
        or len(normalized.encode("utf-8")) > maximum
        or re.search(r"[\x00-\x1f\x7f]", normalized)
    ):
        raise NotebookConfigurationError(f"{label} is invalid.")
    return normalized


def _validate_password(value: str) -> str:
    _reject_placeholder(value, label="PostgreSQL password")
    if not value or len(value.encode("utf-8")) > 4096 or "\x00" in value:
        raise NotebookConfigurationError("PostgreSQL password is invalid.")
    return value


def _reject_placeholder(value: str, *, label: str) -> None:
    lowered = value.lower()
    if (
        not value
        or lowered.startswith("replace-with-")
        or (value.startswith("<") and value.endswith(">"))
    ):
        raise NotebookConfigurationError(f"{label} still contains a placeholder.")


def _bounded_integer(raw: str, *, label: str, minimum: int, maximum: int) -> int:
    if re.fullmatch(r"0|[1-9][0-9]*", raw) is None:
        raise NotebookConfigurationError(f"{label} must be from {minimum} through {maximum}.")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise NotebookConfigurationError(f"{label} must be from {minimum} through {maximum}.")
    return value


__all__ = [
    "NotebookDatabaseSettings",
    "NotebookRuntimeSettings",
    "load_notebook_database_settings",
    "load_notebook_runtime_settings",
    "locate_uploaded_root",
    "notebook_database_connection",
]
