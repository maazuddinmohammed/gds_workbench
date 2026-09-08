"""Environment readiness check for independent Databricks notebooks."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .errors import NotebookConfigurationError, NotebookDatabaseError
from .runtime import (
    NotebookRuntimeSettings,
    load_notebook_runtime_settings,
    notebook_database_connection,
)
from .shared_runtime import (
    create_notebook_workflow_database,
    run_coroutine_in_thread,
)
from .workflow_control import NotebookPrincipal, NotebookWorkflowControlClient


@dataclass(frozen=True, slots=True)
class NotebookPreflightResult:
    python_version: str
    database_ready: bool
    shared_runtime_ready: bool
    unified_auth_ready: bool
    principal_display_name: str
    principal_type: str
    databricks_environment_code: str
    foundry_configured: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "python_version": self.python_version,
            "database_ready": self.database_ready,
            "shared_runtime_ready": self.shared_runtime_ready,
            "unified_auth_ready": self.unified_auth_ready,
            "principal_display_name": self.principal_display_name,
            "principal_type": self.principal_type,
            "databricks_environment_code": self.databricks_environment_code,
            "foundry_configured": self.foundry_configured,
        }


def execute_notebook_preflight(
    settings: NotebookRuntimeSettings,
    *,
    python_version: tuple[int, int] | None = None,
    async_check: Callable[
        [NotebookRuntimeSettings, NotebookPrincipal],
        Coroutine[Any, Any, NotebookPreflightResult],
    ]
    | None = None,
) -> NotebookPreflightResult:
    """Verify DBR Python, fixed identity, shared resources, DB role, and auth."""
    actual_python = python_version or sys.version_info[:2]
    if actual_python != (3, 12):
        raise NotebookConfigurationError(
            "These notebooks require the Python 3.12 image in Databricks Runtime 16.4 LTS."
        )
    with notebook_database_connection(settings.database) as connection:
        principal = NotebookWorkflowControlClient(connection).current_principal()

    checker = async_check or _check_async_runtime
    try:
        return run_coroutine_in_thread(lambda: checker(settings, principal))
    except (NotebookConfigurationError, NotebookDatabaseError):
        raise
    except Exception:
        raise NotebookDatabaseError(
            "Notebook runtime preflight failed without exposing dependency details."
        ) from None


async def _check_async_runtime(
    settings: NotebookRuntimeSettings,
    principal: NotebookPrincipal,
) -> NotebookPreflightResult:
    from databricks.sdk import WorkspaceClient
    from gds_workbench_runtime.profiling import load_default_profiling_policy

    load_default_profiling_policy()
    database = create_notebook_workflow_database(settings.database)

    def check_unified_auth() -> None:
        workspace = WorkspaceClient(
            debug_headers=False,
            product="gds-workbench-notebook",
            product_version="0.1.0",
        )
        headers = workspace.config.authenticate()
        authorization = next(
            (value for name, value in headers.items() if name.lower() == "authorization"), ""
        )
        scheme, _, token = authorization.partition(" ")
        host = urlsplit(workspace.config.host or "")
        if (
            scheme.lower() != "bearer"
            or not token
            or host.scheme != "https"
            or not host.hostname
            or host.username is not None
            or host.password is not None
            or host.path not in {"", "/"}
            or host.query
            or host.fragment
        ):
            raise NotebookDatabaseError(
                "Databricks notebook unified authentication is unavailable."
            )

    await database.open()
    try:
        readiness = await database.readiness()
        if not readiness.ready:
            raise NotebookDatabaseError(
                "Notebook database execution provisioning is incomplete or unavailable."
            )
        await asyncio.to_thread(check_unified_auth)
    finally:
        await database.close()
    return NotebookPreflightResult(
        python_version="3.12",
        database_ready=True,
        shared_runtime_ready=True,
        unified_auth_ready=True,
        principal_display_name=principal.display_name,
        principal_type=principal.principal_type,
        databricks_environment_code=principal.databricks_environment_code,
        foundry_configured=settings.agent_runtime is not None,
    )


def run_notebook_preflight(*, uploaded_root: Path) -> NotebookPreflightResult:
    result = execute_notebook_preflight(load_notebook_runtime_settings(uploaded_root))
    print(json.dumps(result.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return result


__all__ = [
    "NotebookPreflightResult",
    "execute_notebook_preflight",
    "run_notebook_preflight",
]
