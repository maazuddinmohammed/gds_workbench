"""Shared async/database boundary for independent notebook entry points."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from psycopg.conninfo import make_conninfo

from .runtime import NotebookDatabaseSettings


def notebook_database_conninfo(settings: NotebookDatabaseSettings) -> str:
    """Build one internal conninfo from validated fields, never process environment."""
    return make_conninfo(
        host=settings.host,
        port=settings.port,
        dbname=settings.database,
        user=settings.user,
        password=settings.password,
        sslmode=settings.sslmode,
        connect_timeout=settings.connect_timeout_seconds,
        application_name="gds_workbench_databricks_notebook_runtime",
        options=f"-c statement_timeout={settings.statement_timeout_seconds * 1000}",
    )


def create_notebook_workflow_database(settings: NotebookDatabaseSettings) -> Any:
    """Create the shared async adapter without importing the App process."""
    from gds_workbench_api.database import WebPostgresDatabase

    return WebPostgresDatabase(
        dsn=notebook_database_conninfo(settings),
        pool_min=1,
        pool_max=4,
        pool_timeout_seconds=settings.connect_timeout_seconds,
    )


def run_coroutine_in_thread[T](
    factory: Callable[[], Coroutine[Any, Any, T]],
) -> T:
    """Run async notebook work safely when IPython already owns an event loop."""
    with ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="gds-workbench-notebook-runtime"
    ) as executor:
        return executor.submit(lambda: asyncio.run(factory())).result()


__all__ = [
    "create_notebook_workflow_database",
    "notebook_database_conninfo",
    "run_coroutine_in_thread",
]
