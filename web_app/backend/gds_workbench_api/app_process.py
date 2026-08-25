"""Databricks Apps entry point for HTTP and durable workflow execution."""

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from os import environ
from typing import Protocol

import uvicorn
from gds_etl_workbench.configuration import ConfigurationError

from gds_workbench_api.configuration import RuntimeSettings
from gds_workbench_api.runtime import create_runtime_app
from gds_workbench_api.workflow_worker import create_worker_runtime

DATABRICKS_SHUTDOWN_DEADLINE_SECONDS = 15.0
HTTP_SHUTDOWN_SECONDS = 4
COORDINATED_SHUTDOWN_SECONDS = 8.0


class AppServer(Protocol):
    should_exit: bool

    async def serve(self) -> None: ...


class AppWorker(Protocol):
    async def run(self, shutdown: asyncio.Event) -> None: ...


async def run_app_processes(
    *,
    server: AppServer,
    worker: AppWorker,
    shutdown_timeout_seconds: float = COORDINATED_SHUTDOWN_SECONDS,
) -> None:
    """Keep both required runtimes healthy or stop the whole app."""
    shutdown = asyncio.Event()
    server_task = asyncio.create_task(server.serve(), name="workbench-http")
    worker_task = asyncio.create_task(worker.run(shutdown), name="workbench-worker")
    tasks = {server_task, worker_task}
    failure: BaseException | None = None

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                await task
            except BaseException as exc:
                failure = exc
                break
        if failure is None:
            if worker_task in done:
                failure = RuntimeError("the workflow worker stopped unexpectedly")
            elif not server.should_exit:
                failure = RuntimeError("the HTTP server stopped unexpectedly")

        shutdown.set()
        server.should_exit = True
        if pending:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending),
                    timeout=shutdown_timeout_seconds,
                )
            except TimeoutError:
                failure = failure or RuntimeError("app shutdown exceeded its deadline")
    finally:
        shutdown.set()
        server.should_exit = True
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task

    if failure is not None:
        raise failure


def app_port(source: Mapping[str, str] | None = None) -> int:
    values = environ if source is None else source
    raw_port = values.get("DATABRICKS_APP_PORT", "8000").strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ConfigurationError("DATABRICKS_APP_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ConfigurationError("DATABRICKS_APP_PORT must be between 1 and 65535")
    return port


async def _run() -> None:
    settings = RuntimeSettings.from_environment()
    app = create_runtime_app(settings=settings)
    worker = create_worker_runtime(settings=settings)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",  # noqa: S104 - required by the Databricks reverse proxy.
            port=app_port(),
            access_log=False,
            proxy_headers=False,
            server_header=False,
            timeout_graceful_shutdown=HTTP_SHUTDOWN_SECONDS,
        )
    )
    await run_app_processes(server=server, worker=worker)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()


__all__ = [
    "COORDINATED_SHUTDOWN_SECONDS",
    "DATABRICKS_SHUTDOWN_DEADLINE_SECONDS",
    "HTTP_SHUTDOWN_SECONDS",
    "app_port",
    "main",
    "run_app_processes",
]
