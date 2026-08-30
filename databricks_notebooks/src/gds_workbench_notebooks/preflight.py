"""Environment readiness check for independent Databricks notebooks."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

    def as_dict(self) -> dict[str, object]:
        return {
            "python_version": self.python_version,
            "database_ready": self.database_ready,
            "shared_runtime_ready": self.shared_runtime_ready,
            "unified_auth_ready": self.unified_auth_ready,
            "principal_display_name": self.principal_display_name,
            "principal_type": self.principal_type,
            "databricks_environment_code": self.databricks_environment_code,
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
    from gds_workbench_api.capabilities import load_default_agent_capabilities
    from gds_workbench_api.integrations.agents import DatabricksModelAuthentication
    from gds_workbench_runtime.profiling import load_default_profiling_policy

    capabilities = load_default_agent_capabilities()
    if not any(model.provider_code == "databricks" for model in capabilities.models):
        raise NotebookConfigurationError("The Agent registry has no Databricks model deployment.")
    load_default_profiling_policy()
    database = create_notebook_workflow_database(settings.database)
    authentication = DatabricksModelAuthentication(mode="notebook")
    await database.open()
    try:
        readiness = await database.readiness()
        if not readiness.ready:
            raise NotebookDatabaseError(
                "Notebook database execution provisioning is incomplete or unavailable."
            )
        credentials = await authentication.authenticate()
        if not credentials.base_url or not credentials.api_key.get_secret_value():
            raise NotebookDatabaseError(
                "Databricks notebook unified authentication is unavailable."
            )
    finally:
        try:
            await authentication.close()
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
