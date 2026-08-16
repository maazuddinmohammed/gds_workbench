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
        return self.database.scope_rows[: parameters[-1]]


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
    assert database.calls == [(7, 2001)]
    assert database.audit_records[0].input_metadata == {
        "model_id": 7,
        "schema_version": "1.0",
    }
