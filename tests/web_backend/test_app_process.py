import asyncio

import pytest
from gds_etl_workbench.configuration import ConfigurationError

from gds_workbench_api.app_process import (
    COORDINATED_SHUTDOWN_SECONDS,
    DATABRICKS_SHUTDOWN_DEADLINE_SECONDS,
    HTTP_SHUTDOWN_SECONDS,
    app_port,
    run_app_processes,
)


class FakeServer:
    def __init__(self) -> None:
        self.should_exit = False
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def serve(self) -> None:
        self.started.set()
        while not self.should_exit:
            await asyncio.sleep(0)
        self.stopped.set()


class BlockingWorker:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def run(self, shutdown: asyncio.Event) -> None:
        self.started.set()
        await shutdown.wait()
        self.stopped.set()


class FailingWorker(BlockingWorker):
    async def run(self, shutdown: asyncio.Event) -> None:
        del shutdown
        self.started.set()
        raise RuntimeError("bounded worker failure")


@pytest.mark.asyncio
async def test_worker_failure_stops_the_http_server() -> None:
    server = FakeServer()
    worker = FailingWorker()

    with pytest.raises(RuntimeError, match="bounded worker failure"):
        await asyncio.wait_for(
            run_app_processes(server=server, worker=worker),
            timeout=1,
        )

    assert server.stopped.is_set()


@pytest.mark.asyncio
async def test_platform_http_shutdown_stops_the_worker() -> None:
    server = FakeServer()
    worker = BlockingWorker()
    process = asyncio.create_task(run_app_processes(server=server, worker=worker))
    await server.started.wait()
    await worker.started.wait()
    server.should_exit = True

    await asyncio.wait_for(process, timeout=1)

    assert server.stopped.is_set()
    assert worker.stopped.is_set()


def test_databricks_port_is_bounded() -> None:
    assert app_port({}) == 8000
    assert app_port({"DATABRICKS_APP_PORT": "9000"}) == 9000
    with pytest.raises(ConfigurationError, match="must be an integer"):
        app_port({"DATABRICKS_APP_PORT": "not-a-port"})
    with pytest.raises(ConfigurationError, match="must be between"):
        app_port({"DATABRICKS_APP_PORT": "0"})


def test_shutdown_timeouts_leave_platform_termination_margin() -> None:
    assert HTTP_SHUTDOWN_SECONDS + COORDINATED_SHUTDOWN_SECONDS < (
        DATABRICKS_SHUTDOWN_DEADLINE_SECONDS
    )
