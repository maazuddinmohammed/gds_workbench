"""Independent Databricks notebook entry point for governed Tenant Locks."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from .errors import (
    NotebookAuthorizationError,
    NotebookConfigurationError,
    NotebookDatabaseError,
)
from .notebook import WidgetSpec
from .runtime import load_notebook_database_settings, notebook_database_connection

_ACTIONS = ("check", "acquire", "renew", "release")
_DENIAL_CODES = {
    "authorization_denied",
    "tenant_not_found",
    "tenant_locked",
    "tenant_lock_required",
}


@dataclass(frozen=True, slots=True)
class TenantLockRequest:
    action: str
    tenant_id: int
    reason: str | None
    duration_minutes: int | None


@dataclass(frozen=True, slots=True)
class TenantLockResult:
    action: str
    tenant_id: int
    succeeded: bool
    denial_code: str | None = None
    is_locked: bool | None = None
    owned_by_current_principal: bool | None = None
    owner_display_name: str | None = None
    reason: str | None = None
    acquired_time: str | None = None
    expires_time: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "action": self.action,
            "tenant_id": self.tenant_id,
            "succeeded": self.succeeded,
        }
        for key, value in (
            ("denial_code", self.denial_code),
            ("is_locked", self.is_locked),
            ("owned_by_current_principal", self.owned_by_current_principal),
            ("owner_display_name", self.owner_display_name),
            ("reason", self.reason),
            ("acquired_time", self.acquired_time),
            ("expires_time", self.expires_time),
        ):
            if value is not None:
                result[key] = value
        return result


_WIDGETS = (
    WidgetSpec("Action", "check", "Tenant Lock action", _ACTIONS),
    WidgetSpec("TenantID", "", "Tenant ID"),
    WidgetSpec(
        "Reason",
        "Databricks notebook workflow",
        "Lock reason (used by acquire)",
    ),
    WidgetSpec("DurationMinutes", "60", "Lock duration in minutes"),
)


def tenant_lock_widget_specs() -> tuple[WidgetSpec, ...]:
    return _WIDGETS


def create_tenant_lock_widgets(*, dbutils: Any) -> None:
    """Create the visible widget bar for the Tenant Lock notebook."""
    for spec in _WIDGETS:
        if spec.choices:
            dbutils.widgets.dropdown(spec.name, spec.default, list(spec.choices), spec.label)
        else:
            dbutils.widgets.text(spec.name, spec.default, spec.label)


def build_tenant_lock_request(values: Mapping[str, str]) -> TenantLockRequest:
    action = values.get("Action", "").strip()
    if action not in _ACTIONS:
        raise NotebookConfigurationError("Action must be check, acquire, renew, or release.")
    tenant_id = _bounded_integer(
        values.get("TenantID", ""),
        label="TenantID",
        minimum=1,
        maximum=9_223_372_036_854_775_807,
    )
    duration: int | None = None
    if action in {"acquire", "renew"}:
        duration = _bounded_integer(
            values.get("DurationMinutes", ""),
            label="DurationMinutes",
            minimum=1,
            maximum=240,
        )
    reason: str | None = None
    if action == "acquire":
        reason = values.get("Reason", "").strip()
        if not reason or len(reason.encode("utf-8")) > 500 or re.search(r"[\x00-\x1f\x7f]", reason):
            raise NotebookConfigurationError(
                "Reason is required for acquire and must be valid bounded text."
            )
    return TenantLockRequest(
        action=action,
        tenant_id=tenant_id,
        reason=reason,
        duration_minutes=duration,
    )


def execute_tenant_lock_request(connection: Any, request: TenantLockRequest) -> TenantLockResult:
    """Resolve the DB-owned actor and call only the notebook lock wrappers."""
    principal = connection.execute(
        """
        SELECT principal_display_name, databricks_environment_code
          FROM security.current_notebook_principal()
        """
    ).fetchone()
    if principal is None:
        raise NotebookAuthorizationError(
            "The notebook database login has no active Super Admin workload binding."
        )
    _bounded_text(principal.get("principal_display_name"), maximum=200)
    _bounded_text(principal.get("databricks_environment_code"), maximum=100)

    if request.action == "check":
        row = connection.execute(
            """
            SELECT authorized,
                   denial_code,
                   is_locked,
                   owner_display_name,
                   owned_by_current_principal,
                   purpose,
                   acquired_time,
                   expires_time
              FROM security.check_notebook_tenant_lock(%s::BIGINT)
            """,
            (request.tenant_id,),
        ).fetchone()
        result = _required_row(row)
        return TenantLockResult(
            action=request.action,
            tenant_id=request.tenant_id,
            succeeded=_required_boolean(result.get("authorized")),
            denial_code=_denial_code(result.get("denial_code")),
            is_locked=_optional_boolean(result.get("is_locked")),
            owned_by_current_principal=_optional_boolean(result.get("owned_by_current_principal")),
            owner_display_name=_bounded_text(result.get("owner_display_name"), maximum=200),
            reason=_bounded_text(result.get("purpose"), maximum=500),
            acquired_time=_timestamp(result.get("acquired_time")),
            expires_time=_timestamp(result.get("expires_time")),
        )

    if request.action == "acquire":
        row = connection.execute(
            """
            SELECT acquired,
                   denial_code,
                   owner_display_name,
                   purpose,
                   acquired_time,
                   expires_time
              FROM security.acquire_notebook_tenant_lock(
                  %s::BIGINT,
                  %s::INTEGER,
                  %s::VARCHAR
              )
            """,
            (request.tenant_id, request.duration_minutes, request.reason),
        ).fetchone()
        result = _required_row(row)
        succeeded = _required_boolean(result.get("acquired"))
        denial_code = _denial_code(result.get("denial_code"))
        return TenantLockResult(
            action=request.action,
            tenant_id=request.tenant_id,
            succeeded=succeeded,
            denial_code=denial_code,
            is_locked=True if succeeded or denial_code == "tenant_locked" else None,
            owner_display_name=_bounded_text(result.get("owner_display_name"), maximum=200),
            reason=_bounded_text(result.get("purpose"), maximum=500),
            acquired_time=_timestamp(result.get("acquired_time")),
            expires_time=_timestamp(result.get("expires_time")),
        )

    if request.action == "renew":
        row = connection.execute(
            """
            SELECT renewed,
                   denial_code,
                   owner_display_name,
                   purpose,
                   acquired_time,
                   expires_time
              FROM security.renew_notebook_tenant_lock(
                  %s::BIGINT,
                  %s::INTEGER
              )
            """,
            (request.tenant_id, request.duration_minutes),
        ).fetchone()
        result = _required_row(row)
        succeeded = _required_boolean(result.get("renewed"))
        denial_code = _denial_code(result.get("denial_code"))
        return TenantLockResult(
            action=request.action,
            tenant_id=request.tenant_id,
            succeeded=succeeded,
            denial_code=denial_code,
            is_locked=True if succeeded or denial_code == "tenant_locked" else None,
            owner_display_name=_bounded_text(result.get("owner_display_name"), maximum=200),
            reason=_bounded_text(result.get("purpose"), maximum=500),
            acquired_time=_timestamp(result.get("acquired_time")),
            expires_time=_timestamp(result.get("expires_time")),
        )

    row = connection.execute(
        """
        SELECT released,
               denial_code,
               owner_display_name,
               acquired_time,
               expires_time
          FROM security.release_notebook_tenant_lock(%s::BIGINT)
        """,
        (request.tenant_id,),
    ).fetchone()
    result = _required_row(row)
    succeeded = _required_boolean(result.get("released"))
    denial_code = _denial_code(result.get("denial_code"))
    return TenantLockResult(
        action=request.action,
        tenant_id=request.tenant_id,
        succeeded=succeeded,
        denial_code=denial_code,
        is_locked=False if succeeded else None,
        owner_display_name=_bounded_text(result.get("owner_display_name"), maximum=200),
        acquired_time=_timestamp(result.get("acquired_time")),
        expires_time=_timestamp(result.get("expires_time")),
    )


def run_tenant_lock_notebook(
    *,
    dbutils: Any,
    uploaded_root: Path,
    connector: Callable[..., Any] | None = None,
) -> TenantLockResult:
    """Read existing widgets, run one lock action, and print bounded JSON."""
    values = {spec.name: dbutils.widgets.get(spec.name) for spec in _WIDGETS}
    request = build_tenant_lock_request(values)
    settings = load_notebook_database_settings(uploaded_root)
    connection_context = (
        notebook_database_connection(settings)
        if connector is None
        else notebook_database_connection(settings, connector=connector)
    )
    with connection_context as connection:
        result = execute_tenant_lock_request(connection, request)
    print(json.dumps(result.as_dict(), sort_keys=True, separators=(",", ":")))
    return result


def _required_row(row: Any) -> Mapping[str, Any]:
    if not isinstance(row, Mapping):
        raise NotebookDatabaseError("The notebook database returned an invalid lock result.")
    return cast(Mapping[str, Any], row)


def _denial_code(value: Any) -> str | None:
    if value is None:
        return None
    if value not in _DENIAL_CODES:
        raise NotebookDatabaseError("The notebook database returned an invalid denial code.")
    return str(value)


def _optional_boolean(value: Any) -> bool | None:
    if value is None or type(value) is bool:
        return value
    raise NotebookDatabaseError("The notebook database returned an invalid lock result.")


def _required_boolean(value: Any) -> bool:
    if type(value) is bool:
        return value
    raise NotebookDatabaseError("The notebook database returned an invalid lock result.")


def _bounded_text(value: Any, *, maximum: int) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise NotebookDatabaseError("The notebook database returned invalid bounded text.")
    return value


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise NotebookDatabaseError("The notebook database returned an invalid timestamp.")
    return value.isoformat()


def _bounded_integer(raw: str, *, label: str, minimum: int, maximum: int) -> int:
    value = raw.strip()
    if re.fullmatch(r"0|[1-9][0-9]*", value) is None:
        raise NotebookConfigurationError(f"{label} must be from {minimum} through {maximum}.")
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise NotebookConfigurationError(f"{label} must be from {minimum} through {maximum}.")
    return parsed


__all__ = [
    "TenantLockRequest",
    "TenantLockResult",
    "build_tenant_lock_request",
    "execute_tenant_lock_request",
    "run_tenant_lock_notebook",
    "tenant_lock_widget_specs",
]
