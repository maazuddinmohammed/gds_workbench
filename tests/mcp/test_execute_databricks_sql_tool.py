from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, LiteralString
from uuid import uuid4

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import TextContent

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.errors import (
    DatabricksStatementFailedError,
    DependencyUnavailableError,
)
from gds_etl_workbench.infrastructure.postgres import (
    DatabricksConnectionValuesRecord,
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
)
from gds_etl_workbench.tools.databricks.execute_sql import (
    register_execute_databricks_sql_tool,
)
from gds_etl_workbench.tools.databricks.executor import (
    DatabricksSqlConnection,
    DatabricksSqlExecutionResult,
)
from gds_etl_workbench.tools.databricks.validation import ValidatedDatabricksSql


@dataclass
class FakeDatabase:
    connection_row: dict[str, Any] | None
    values: DatabricksConnectionValuesRecord
    lookup_failure: Exception | None = None
    audit_records: list[ToolCallLogRecord] = field(
        default_factory=lambda: list[ToolCallLogRecord]()
    )
    lookup_ids: list[int] = field(default_factory=lambda: list[int]())

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def readiness(self) -> ReadinessRecord:
        return ReadinessRecord(ready=True, code="ready")

    async def expire_tenant_locks(self) -> int:
        return 0

    async def append_tool_call_log(self, record: ToolCallLogRecord) -> None:
        self.audit_records.append(record)

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        yield FakeReadTransaction(self)

    async def read_databricks_connection_values(
        self,
        connection_id: int,
    ) -> DatabricksConnectionValuesRecord:
        self.lookup_ids.append(connection_id)
        if self.lookup_failure is not None:
            raise self.lookup_failure
        return self.values


@dataclass
class FakeReadTransaction:
    database: FakeDatabase

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        assert parameters == (42,)
        return self.database.connection_row

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError("not used")


@dataclass
class FakeExecutor:
    result: DatabricksSqlExecutionResult = DatabricksSqlExecutionResult(
        columns=("answer",),
        rows=((1,),),
        rows_truncated=False,
        cells_truncated=False,
    )
    failure: Exception | None = None
    calls: list[tuple[DatabricksSqlConnection, ValidatedDatabricksSql, int, int]] = (
        field(
            default_factory=lambda: list[
                tuple[DatabricksSqlConnection, ValidatedDatabricksSql, int, int]
            ]()
        )
    )

    async def execute(
        self,
        *,
        connection: DatabricksSqlConnection,
        batch: ValidatedDatabricksSql,
        max_rows: int,
        timeout_seconds: int,
    ) -> DatabricksSqlExecutionResult:
        self.calls.append((connection, batch, max_rows, timeout_seconds))
        if self.failure is not None:
            raise self.failure
        return self.result


def _values(
    *,
    failure_code: str | None = None,
    tenant_id: int | None = 7,
) -> DatabricksConnectionValuesRecord:
    return DatabricksConnectionValuesRecord(
        tenant_id=tenant_id,
        failure_code=failure_code,
        server_hostname=("workspace.example.invalid" if failure_code is None else None),
        http_path=("/sql/1.0/warehouses/abc-123" if failure_code is None else None),
        access_token=uuid4().hex if failure_code is None else None,
    )


def _server(
    database: FakeDatabase,
    executor: FakeExecutor,
) -> MCPServer[None]:
    identity = IdentityProvider(AuthMode.DEV)
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="databricks-sql-test", middleware=[audit])
    register_execute_databricks_sql_tool(
        server,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
        executor=executor,
        max_rows=50,
        timeout_seconds=120,
    )
    return server


@pytest.mark.asyncio
async def test_tool_executes_governed_batch_and_returns_final_result() -> None:
    values = _values()
    database = FakeDatabase({"tenant_id": 7}, values)
    executor = FakeExecutor(
        DatabricksSqlExecutionResult(
            columns=("answer",),
            rows=((1,), (2,)),
            rows_truncated=True,
            cells_truncated=False,
        )
    )
    sql = "CREATE TEMP VIEW scratch AS SELECT 1; SELECT * FROM scratch"

    async with Client(_server(database, executor)) as client:
        result = await client.call_tool(
            "execute_databricks_sql",
            {"connection_id": 42, "sql": sql},
        )

    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "connection_id": 42,
        "statement_count": 2,
        "row_limit": 50,
        "columns": ["answer"],
        "rows": [[1], [2]],
        "row_count": 2,
        "rows_truncated": True,
        "cells_truncated": False,
    }
    assert database.lookup_ids == [42]
    assert len(executor.calls) == 1
    connection, batch, max_rows, timeout = executor.calls[0]
    assert [statement.sql for statement in batch.statements] == [
        "CREATE TEMP VIEW scratch AS SELECT 1",
        "SELECT * FROM scratch",
    ]
    assert max_rows == 50
    assert timeout == 120
    assert database.audit_records[0].input_metadata == {
        "schema_version": "1.0",
        "connection_id": 42,
        "sql": sql,
        "sql_character_count": len(sql),
    }
    rendered_audit = repr(database.audit_records)
    assert sql in rendered_audit
    assert connection.access_token not in rendered_audit


@pytest.mark.parametrize(
    ("failure_code", "expected_code"),
    [
        (
            "connection_values_missing",
            "databricks_connection_configuration_missing",
        ),
        (
            "connection_values_ambiguous",
            "databricks_connection_configuration_ambiguous",
        ),
        ("connection_not_found", "databricks_connection_not_found"),
    ],
)
@pytest.mark.asyncio
async def test_tool_returns_missing_or_ambiguous_configuration_gracefully(
    failure_code: str,
    expected_code: str,
) -> None:
    database = FakeDatabase({"tenant_id": 7}, _values(failure_code=failure_code))
    executor = FakeExecutor()

    async with Client(_server(database, executor)) as client:
        result = await client.call_tool(
            "execute_databricks_sql",
            {"connection_id": 42, "sql": "SELECT 1"},
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert expected_code in result.content[0].text
    assert executor.calls == []


@pytest.mark.asyncio
async def test_tool_returns_missing_global_connection_gracefully() -> None:
    database = FakeDatabase(None, _values())
    executor = FakeExecutor()

    async with Client(_server(database, executor)) as client:
        result = await client.call_tool(
            "execute_databricks_sql",
            {"connection_id": 42, "sql": "SELECT 1"},
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert "databricks_connection_not_found" in result.content[0].text
    assert database.lookup_ids == []
    assert executor.calls == []


@pytest.mark.asyncio
async def test_tool_returns_connection_value_read_failure_gracefully() -> None:
    database = FakeDatabase(
        {"tenant_id": 7},
        _values(),
        lookup_failure=DependencyUnavailableError(),
    )
    executor = FakeExecutor()

    async with Client(_server(database, executor)) as client:
        result = await client.call_tool(
            "execute_databricks_sql",
            {"connection_id": 42, "sql": "SELECT 1"},
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert "dependency_unavailable" in result.content[0].text
    assert executor.calls == []


@pytest.mark.asyncio
async def test_tool_rejects_dml_before_reading_connection_values() -> None:
    database = FakeDatabase({"tenant_id": 7}, _values())
    executor = FakeExecutor()

    async with Client(_server(database, executor)) as client:
        result = await client.call_tool(
            "execute_databricks_sql",
            {"connection_id": 42, "sql": "DELETE FROM bronze.customer"},
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert "invalid_request" in result.content[0].text
    assert database.lookup_ids == []
    assert executor.calls == []


@pytest.mark.asyncio
async def test_tool_returns_databricks_statement_failure_gracefully() -> None:
    database = FakeDatabase({"tenant_id": 7}, _values())
    executor = FakeExecutor(failure=DatabricksStatementFailedError(2))

    async with Client(_server(database, executor)) as client:
        result = await client.call_tool(
            "execute_databricks_sql",
            {"connection_id": 42, "sql": "SELECT 1; SELECT 2"},
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert "databricks_statement_failed" in result.content[0].text
    assert "statement 2" in result.content[0].text


@pytest.mark.asyncio
async def test_tool_redacts_unexpected_failure_details() -> None:
    private_detail = f"private-{uuid4().hex}"
    values = _values()
    database = FakeDatabase({"tenant_id": 7}, values)
    executor = FakeExecutor(failure=RuntimeError(private_detail))

    async with Client(_server(database, executor)) as client:
        result = await client.call_tool(
            "execute_databricks_sql",
            {"connection_id": 42, "sql": "SELECT 1"},
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    returned = result.content[0].text
    assert values.access_token is not None
    assert "internal_error" in returned
    assert private_detail not in returned
    assert values.access_token not in returned
    assert private_detail not in repr(database.audit_records)
