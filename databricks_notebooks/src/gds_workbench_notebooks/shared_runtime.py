"""Shared async/database boundary for independent notebook entry points."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from typing import Any

from psycopg.conninfo import make_conninfo

from .errors import NotebookDatabaseError
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
    result: list[T] = []
    failure: list[BaseException] = []

    def target() -> None:
        try:
            result.append(asyncio.run(factory()))
        except BaseException as error:
            failure.append(error)

    thread = threading.Thread(
        target=target,
        name="gds-workbench-notebook-runtime",
        daemon=False,
    )
    thread.start()
    thread.join()
    if failure:
        raise failure[0]
    if len(result) != 1:
        raise NotebookDatabaseError("Notebook runtime returned no result.")
    return result[0]


__all__ = [
    "create_notebook_workflow_database",
    "notebook_database_conninfo",
    "run_coroutine_in_thread",
]
