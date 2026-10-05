"""MCP profiling batch selection and cancellation behavior."""

import asyncio
import threading
from typing import Any

import pytest

from gds_etl_workbench.application.profiling.execution import (
    ConnectorProfilingExecutor,
    ProfileAttribute,
    ProfileObject,
    ProfileQuery,
    build_profile_queries,
    validate_batch_ids,
)
from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.domain.errors import InvalidRequestError


@pytest.mark.parametrize(
    ("value", "data_type"),
    [
        ("1.1", "INT"),
        ("256", "TINYINT"),
        ("x", "BOOLEAN"),
        ("2026-02-30", "DATE"),
        ("1.234", "DECIMAL(4,2)"),
        ("1", "FLOAT"),
        ("2026-01-01 00:00:00", "TIMESTAMP"),
        ("2026-01-01 00:00:00Z", "TIMESTAMP_NTZ"),
        ("abcd", "VARCHAR(3)"),
    ],
)
def test_batch_casts_cannot_silently_change_population(
    value: str, data_type: str
) -> None:
    with pytest.raises(InvalidRequestError):
        validate_batch_ids((value,), data_type)


def test_batch_values_remain_parameters_and_single_id_uses_in() -> None:
    target = ProfileObject(
        object_id=1,
        connection_id=1,
        catalog="catalog",
        schema="schema",
        table="table",
        batch_attribute_name="batch",
        attributes=(
            ProfileAttribute(attribute_id=1, name="batch", data_type="STRING"),
        ),
    )
    batch = "a'); DROP TABLE dangerous; --"
    query = build_profile_queries(target, batch_ids=(batch,), require_batch_ids=True)[0]
    assert batch not in query.sql
    assert query.parameters == (batch,)
    assert "IN (CAST(? AS STRING))" in query.sql
    with pytest.raises(InvalidRequestError):
        build_profile_queries(target, require_batch_ids=True)


@pytest.mark.asyncio
async def test_cancelling_executor_requests_databricks_statement_cancellation() -> None:
    started = threading.Event()
    cancelled = threading.Event()

    class Cursor:
        description = None

        def execute(self, *_: Any) -> None:
            started.set()
            cancelled.wait(5)

        def cancel(self) -> None:
            cancelled.set()

        def fetchmany(self, _: int) -> list[Any]:
            return []

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    class Connection:
        def cursor(self) -> Any:
            return Cursor()

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *_: Any) -> None:
            pass

    executor = ConnectorProfilingExecutor(connect=lambda **_: Connection())
    task = asyncio.create_task(
        executor.execute(
            connection=DatabricksSqlConnection(
                server_hostname="fixture.invalid",
                http_path="/fixture",
                access_token="fixture",
            ),
            query=ProfileQuery(1, (1,), "SELECT aggregate_only", ()),
            timeout_seconds=5,
        )
    )
    assert await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
