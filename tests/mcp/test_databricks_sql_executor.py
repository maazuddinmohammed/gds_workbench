from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from types import TracebackType
from typing import Self
from uuid import uuid4

import pytest

from gds_etl_workbench.domain.errors import (
    DatabricksConnectionFailedError,
    DatabricksResultTooLargeError,
    DatabricksStatementFailedError,
)
from gds_etl_workbench.infrastructure.databricks_sql import (
    ConnectorDatabricksSqlExecutor,
    DatabricksError,
    DatabricksSqlConnection,
)
from gds_etl_workbench.domain.databricks_sql import validate_databricks_sql


class FakeCursor:
    def __init__(
        self,
        *,
        description: list[tuple[object, ...]] | None,
        rows: list[tuple[object, ...]],
        failure_index: int | None = None,
    ) -> None:
        self.description = description
        self.rows = rows
        self.failure_index = failure_index
        self.executed: list[str] = []
        self.fetch_sizes: list[int] = []

    def execute(self, operation: str) -> object:
        self.executed.append(operation)
        if len(self.executed) == self.failure_index:
            raise DatabricksError("generated connector detail must remain private")
        return None

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        self.fetch_sizes.append(size)
        return self.rows[:size]

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class CapturingConnect:
    def __init__(
        self,
        connection: FakeConnection | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.connection = connection
        self.failure = failure
        self.arguments: dict[str, object] = {}

    def __call__(self, **kwargs: object) -> FakeConnection:
        self.arguments = kwargs
        if self.failure is not None:
            raise self.failure
        assert self.connection is not None
        return self.connection


class LoggingConnect(CapturingConnect):
    def __call__(self, **kwargs: object) -> FakeConnection:
        logging.getLogger("databricks.sql.client").warning(
            "connector detail %s",
            kwargs["access_token"],
        )
        return super().__call__(**kwargs)


def _connection() -> DatabricksSqlConnection:
    return DatabricksSqlConnection(
        server_hostname="workspace.example.invalid",
        http_path="/sql/1.0/warehouses/abc-123",
        access_token=uuid4().hex,
    )


@pytest.mark.asyncio
async def test_executor_runs_all_statements_and_returns_only_50_final_rows() -> None:
    cursor = FakeCursor(
        description=[("answer", None, None, None, None, None, None)],
        rows=[(index,) for index in range(51)],
    )
    connect = CapturingConnect(FakeConnection(cursor))
    executor = ConnectorDatabricksSqlExecutor(connect)
    connection = _connection()
    batch = validate_databricks_sql(
        "CREATE TEMP VIEW recent AS SELECT 1; "
        "CREATE TEMP TABLE scratch AS SELECT 2; "
        "SELECT * FROM scratch"
    )

    result = await executor.execute(
        connection=connection,
        batch=batch,
        max_rows=50,
        timeout_seconds=90,
    )

    assert cursor.executed == [statement.sql for statement in batch.statements]
    assert cursor.fetch_sizes == [51]
    assert result.columns == ("answer",)
    assert result.rows == tuple((index,) for index in range(50))
    assert result.rows_truncated is True
    assert result.cells_truncated is False
    assert connect.arguments == {
        "server_hostname": connection.server_hostname,
        "http_path": connection.http_path,
        "access_token": connection.access_token,
        "session_configuration": {"STATEMENT_TIMEOUT": "90"},
        "user_agent_entry": "gds-etl-workbench",
        "use_cloud_fetch": False,
        "enable_telemetry": 0,
        "_socket_timeout": 90,
        "_retry_stop_after_attempts_count": 3,
        "_use_arrow_native_complex_types": False,
    }


@pytest.mark.asyncio
async def test_executor_returns_empty_result_for_final_temporary_ddl() -> None:
    cursor = FakeCursor(description=None, rows=[])
    executor = ConnectorDatabricksSqlExecutor(CapturingConnect(FakeConnection(cursor)))

    result = await executor.execute(
        connection=_connection(),
        batch=validate_databricks_sql("CREATE TEMP VIEW scratch AS SELECT 1"),
        max_rows=50,
        timeout_seconds=120,
    )

    assert result.columns == ()
    assert result.rows == ()
    assert cursor.fetch_sizes == []


@pytest.mark.asyncio
async def test_executor_serializes_cells_to_bounded_json_values() -> None:
    cursor = FakeCursor(
        description=[
            ("decimal_value",),
            ("timestamp_value",),
            ("binary_value",),
            ("long_value",),
        ],
        rows=[
            (
                Decimal("1.25"),
                datetime(2026, 8, 15, tzinfo=UTC),
                b"abc",
                "x" * 20_001,
            )
        ],
    )
    executor = ConnectorDatabricksSqlExecutor(CapturingConnect(FakeConnection(cursor)))

    result = await executor.execute(
        connection=_connection(),
        batch=validate_databricks_sql("SELECT 1"),
        max_rows=50,
        timeout_seconds=120,
    )

    assert result.rows[0][:3] == (
        "1.25",
        "2026-08-15T00:00:00+00:00",
        "base64:YWJj",
    )
    assert result.rows[0][3] == "x" * 20_000
    assert result.cells_truncated is True


@pytest.mark.asyncio
async def test_executor_returns_safe_connection_failure() -> None:
    private_detail = f"private-{uuid4().hex}"
    executor = ConnectorDatabricksSqlExecutor(
        CapturingConnect(failure=DatabricksError(private_detail))
    )

    with pytest.raises(DatabricksConnectionFailedError) as caught:
        await executor.execute(
            connection=_connection(),
            batch=validate_databricks_sql("SELECT 1"),
            max_rows=50,
            timeout_seconds=120,
        )

    assert private_detail not in str(caught.value)


@pytest.mark.asyncio
async def test_executor_returns_safe_failing_statement_index() -> None:
    cursor = FakeCursor(description=None, rows=[], failure_index=2)
    executor = ConnectorDatabricksSqlExecutor(CapturingConnect(FakeConnection(cursor)))

    with pytest.raises(DatabricksStatementFailedError) as caught:
        await executor.execute(
            connection=_connection(),
            batch=validate_databricks_sql("SELECT 1; SELECT 2"),
            max_rows=50,
            timeout_seconds=120,
        )

    assert caught.value.code == "databricks_statement_failed"
    assert "statement 2" in str(caught.value)
    assert "connector detail" not in str(caught.value)


@pytest.mark.asyncio
async def test_executor_rejects_more_than_500_columns() -> None:
    cursor = FakeCursor(
        description=[(f"column_{index}",) for index in range(501)],
        rows=[],
    )
    executor = ConnectorDatabricksSqlExecutor(CapturingConnect(FakeConnection(cursor)))

    with pytest.raises(DatabricksResultTooLargeError):
        await executor.execute(
            connection=_connection(),
            batch=validate_databricks_sql("SELECT 1"),
            max_rows=50,
            timeout_seconds=120,
        )


@pytest.mark.asyncio
async def test_executor_enforces_the_hard_50_row_cap() -> None:
    cursor = FakeCursor(description=[("answer",)], rows=[])
    connect = CapturingConnect(FakeConnection(cursor))
    executor = ConnectorDatabricksSqlExecutor(connect)

    with pytest.raises(DatabricksResultTooLargeError):
        await executor.execute(
            connection=_connection(),
            batch=validate_databricks_sql("SELECT 1"),
            max_rows=51,
            timeout_seconds=120,
        )

    assert connect.arguments == {}


def test_connection_repr_never_contains_connection_values() -> None:
    connection = _connection()

    rendered = repr(connection)
    assert connection.server_hostname not in rendered
    assert connection.http_path not in rendered
    assert connection.access_token not in rendered


@pytest.mark.asyncio
async def test_connector_namespace_cannot_log_connection_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cursor = FakeCursor(description=None, rows=[])
    executor = ConnectorDatabricksSqlExecutor(LoggingConnect(FakeConnection(cursor)))
    connection = _connection()
    caplog.set_level(logging.DEBUG)

    await executor.execute(
        connection=connection,
        batch=validate_databricks_sql("SELECT 1"),
        max_rows=50,
        timeout_seconds=120,
    )

    assert connection.access_token not in caplog.text
    assert "connector detail" not in caplog.text
