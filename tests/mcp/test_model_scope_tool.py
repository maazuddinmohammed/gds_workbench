from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, LiteralString

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
)
from gds_etl_workbench.tools.modeling.model_scope import (
    GetModelScopeResult,
    register_get_model_scope_tool,
)


@dataclass
class FakeDatabase:
    scope_rows: list[dict[str, Any]]
    audit_records: list[ToolCallLogRecord] = field(default_factory=list)
    calls: list[tuple[Any, ...]] = field(default_factory=list)

    async def open(self) -> None: ...

    async def close(self) -> None: ...

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
    ) -> AsyncIterator[ReadTransaction]:
        yield FakeReadTransaction(self)


@dataclass
class FakeReadTransaction:
    database: FakeDatabase

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        assert parameters == (7,)
        return {
            "model_id": 7,
            "tenant_id": 3,
            "model_name": "Northwind",
            "model_revision": 4,
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "model_scope.is_active" in query
        self.database.calls.append(parameters)
        limit, offset = parameters[-2:]
        return self.database.scope_rows[offset : offset + limit]


def _server(database: FakeDatabase) -> MCPServer[None]:
    identity = IdentityProvider(AuthMode.DEV)
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-scope-test", middleware=[audit])
    register_get_model_scope_tool(
        server,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    return server


def _scope_row() -> dict[str, Any]:
    return {
        "model_scope_id": 9,
        "object_id": 11,
        "tenant_id": 3,
        "tenant_code": "northwind",
        "tenant_name": "Northwind",
        "system_id": 5,
        "system_code": "erp",
        "system_name": "ERP",
        "connection_id": 6,
        "connection_code": "source",
        "connection_name": "Source",
        "object_schema": "sales",
        "object_name": "orders",
        "object_type_id": 2,
        "object_type_code": "table",
        "object_type_name": "Table",
        "zone_code": "model_tool_raw",
        "model_scope_is_locked": False,
        "is_active": True,
        "total_object_count": 1,
    }


@pytest.mark.asyncio
async def test_get_model_scope_returns_expanded_active_objects() -> None:
    database = FakeDatabase(scope_rows=[_scope_row()])

    async with Client(_server(database)) as client:
        call = await client.call_tool("get_model_scope", {"model_id": 7})

    result = GetModelScopeResult.model_validate(call.structured_content)
    assert result.model_id == 7
    assert result.model_revision == 4
    assert result.object_count == 1
    assert result.objects[0].object_id == 11
    assert result.objects[0].tenant_code == "northwind"
    assert result.objects[0].object_name == "orders"
    assert result.objects[0].zone_code == "model_tool_raw"
    assert result.objects[0].is_active is True
    assert database.calls == [(7, 2001, 0)]
    assert database.audit_records[0].input_metadata == {
        "model_id": 7,
        "schema_version": "1.0",
        "page_size": 2000,
        "cursor_provided": False,
    }


@pytest.mark.asyncio
async def test_get_model_scope_recovers_every_object_across_pages() -> None:
    rows = [
        {
            **_scope_row(),
            "model_scope_id": object_id,
            "object_id": object_id,
            "object_name": f"object_{object_id}",
            "total_object_count": 3,
        }
        for object_id in range(1, 4)
    ]
    database = FakeDatabase(scope_rows=rows)

    async with Client(_server(database)) as client:
        first_call = await client.call_tool(
            "get_model_scope",
            {"model_id": 7, "page_size": 1},
        )
        first = GetModelScopeResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        second_call = await client.call_tool(
            "get_model_scope",
            {"model_id": 7, "page_size": 1, "cursor": first.next_cursor},
        )
        second = GetModelScopeResult.model_validate(second_call.structured_content)
        assert second.next_cursor is not None
        third_call = await client.call_tool(
            "get_model_scope",
            {"model_id": 7, "page_size": 1, "cursor": second.next_cursor},
        )
        third = GetModelScopeResult.model_validate(third_call.structured_content)

    assert [item.object_id for item in first.objects] == [1]
    assert [item.object_id for item in second.objects] == [2]
    assert [item.object_id for item in third.objects] == [3]
    assert third.next_cursor is None
    assert database.calls == [(7, 2, 0), (7, 2, 1), (7, 2, 2)]


@pytest.mark.asyncio
async def test_get_model_scope_rejects_a_tampered_cursor_before_querying_scope() -> None:
    rows = [
        {**_scope_row(), "object_id": object_id, "total_object_count": 2}
        for object_id in range(1, 3)
    ]
    database = FakeDatabase(scope_rows=rows)

    async with Client(_server(database)) as client:
        first_call = await client.call_tool(
            "get_model_scope",
            {"model_id": 7, "page_size": 1},
        )
        first = GetModelScopeResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        replacement = "A" if first.next_cursor[0] != "A" else "B"
        rejected = await client.call_tool(
            "get_model_scope",
            {
                "model_id": 7,
                "page_size": 1,
                "cursor": f"{replacement}{first.next_cursor[1:]}",
            },
        )

    assert rejected.is_error is True
    assert database.calls == [(7, 2, 0)]


@pytest.mark.asyncio
async def test_get_model_scope_cursor_is_bound_to_model_and_page_size() -> None:
    rows = [
        {**_scope_row(), "object_id": object_id, "total_object_count": 2}
        for object_id in range(1, 3)
    ]
    database = FakeDatabase(scope_rows=rows)

    async with Client(_server(database)) as client:
        first_call = await client.call_tool(
            "get_model_scope",
            {"model_id": 7, "page_size": 1},
        )
        first = GetModelScopeResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        wrong_model = await client.call_tool(
            "get_model_scope",
            {"model_id": 8, "page_size": 1, "cursor": first.next_cursor},
        )
        wrong_page_size = await client.call_tool(
            "get_model_scope",
            {"model_id": 7, "page_size": 2, "cursor": first.next_cursor},
        )

    assert wrong_model.is_error is True
    assert wrong_page_size.is_error is True
    assert database.calls == [(7, 2, 0)]


@pytest.mark.asyncio
async def test_get_model_scope_advertises_bounded_pagination_inputs() -> None:
    async with Client(_server(FakeDatabase(scope_rows=[]))) as client:
        tools = await client.list_tools()

    schema = next(
        tool.input_schema for tool in tools.tools if tool.name == "get_model_scope"
    )
    assert schema["properties"]["page_size"] == {
        "default": 2000,
        "maximum": 2000,
        "minimum": 1,
        "title": "Page Size",
        "type": "integer",
    }
    assert schema["properties"]["cursor"]["anyOf"] == [
        {"maxLength": 2048, "type": "string"},
        {"type": "null"},
    ]
