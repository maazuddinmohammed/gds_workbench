from __future__ import annotations

from collections.abc import AsyncGenerator
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
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
)
from gds_etl_workbench.tools.modeling.model_input_scope import (
    GetModelInputScopeResult,
    register_get_model_input_scope_tool,
)


@dataclass
class FakeDatabase:
    rows: list[dict[str, Any]]
    calls: list[tuple[Any, ...]] = field(default_factory=list)
    audit_records: list[ToolCallLogRecord] = field(default_factory=list)

    async def append_tool_call_log(self, record: ToolCallLogRecord) -> None:
        self.audit_records.append(record)

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        del isolation
        yield FakeReadTransaction(self)


@dataclass
class FakeReadTransaction:
    database: FakeDatabase

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        del query
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
        assert "model.model_input_scope" in query
        assert "object.source_tenant_id = model.tenant_id" in query
        assert "zone.zone_code IN ('source', 'bronze')" in query
        assert "source_tenant.tenant_code AS source_tenant_code" in query
        assert "placement_tenant.tenant_code AS placement_tenant_code" in query
        self.database.calls.append(parameters)
        limit, offset = parameters[-2:]
        return self.database.rows[offset : offset + limit]


def server(database: FakeDatabase) -> MCPServer[None]:
    identity = IdentityProvider(AuthMode.DEV)
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
    )
    result = MCPServer[None](name="model-input-scope-test", middleware=[audit])
    register_get_model_input_scope_tool(
        result,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    return result


def scope_row(
    *,
    object_id: int = 11,
    object_name: str = "orders",
    zone_code: str = "source",
    total: int = 1,
) -> dict[str, Any]:
    return {
        "model_input_scope_id": object_id + 100,
        "object_id": object_id,
        "source_tenant_id": 3,
        "source_tenant_code": "northwind",
        "source_tenant_name": "Northwind",
        "placement_tenant_id": 3 if zone_code == "source" else 9,
        "placement_tenant_code": "northwind" if zone_code == "source" else "gds",
        "placement_tenant_name": "Northwind" if zone_code == "source" else "GDS",
        "system_id": 5,
        "system_code": "erp" if zone_code == "source" else "gds",
        "system_name": "ERP" if zone_code == "source" else "GDS",
        "connection_id": 6,
        "connection_code": "fc" if zone_code == "source" else "lakehouse",
        "connection_name": "Foreign Catalog" if zone_code == "source" else "Lakehouse",
        "foreign_catalog": "foreign_main" if zone_code == "source" else None,
        "object_schema": "sales" if zone_code == "source" else "bronze",
        "object_name": object_name,
        "fc_object_schema": "sales_fc" if zone_code == "source" else None,
        "fc_object_name": f"{object_name}_fc" if zone_code == "source" else None,
        "object_type_id": 2,
        "object_type_code": "table",
        "object_type_name": "Table",
        "zone_code": zone_code,
        "model_input_scope_is_locked": False,
        "is_active": True,
        "total_object_count": total,
    }


@pytest.mark.asyncio
async def test_get_model_input_scope_returns_source_ownership_and_placement() -> None:
    database = FakeDatabase(
        rows=[
            scope_row(total=2),
            scope_row(
                object_id=12, object_name="orders_bronze", zone_code="bronze", total=2
            ),
        ]
    )

    async with Client(server(database)) as client:
        call = await client.call_tool("get_model_input_scope", {"model_id": 7})

    result = GetModelInputScopeResult.model_validate(call.structured_content)
    assert result.model_id == 7
    assert result.model_revision == 4
    assert result.object_count == 2
    assert [item.zone_code for item in result.objects] == ["source", "bronze"]
    source, bronze = result.objects
    assert source.source_tenant_code == "northwind"
    assert source.placement_tenant_code == "northwind"
    assert source.foreign_catalog == "foreign_main"
    assert source.fc_object_schema == "sales_fc"
    assert source.fc_object_name == "orders_fc"
    assert bronze.source_tenant_code == "northwind"
    assert bronze.placement_tenant_code == "gds"
    assert bronze.foreign_catalog is None
    assert database.calls == [(7, 2001, 0)]
    assert database.audit_records[0].input_metadata == {
        "model_id": 7,
        "schema_version": "1.0",
        "page_size": 2000,
        "cursor_provided": False,
    }


@pytest.mark.asyncio
async def test_get_model_input_scope_paginates_with_bound_cursor() -> None:
    database = FakeDatabase(
        rows=[
            scope_row(object_id=index, object_name=f"object_{index}", total=3)
            for index in range(1, 4)
        ]
    )

    async with Client(server(database)) as client:
        first_call = await client.call_tool(
            "get_model_input_scope",
            {"model_id": 7, "page_size": 1},
        )
        first = GetModelInputScopeResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        second_call = await client.call_tool(
            "get_model_input_scope",
            {"model_id": 7, "page_size": 1, "cursor": first.next_cursor},
        )
        second = GetModelInputScopeResult.model_validate(second_call.structured_content)
        assert second.next_cursor is not None
        third_call = await client.call_tool(
            "get_model_input_scope",
            {"model_id": 7, "page_size": 1, "cursor": second.next_cursor},
        )
        third = GetModelInputScopeResult.model_validate(third_call.structured_content)

    assert [item.object_id for item in first.objects] == [1]
    assert [item.object_id for item in second.objects] == [2]
    assert [item.object_id for item in third.objects] == [3]
    assert third.next_cursor is None
    assert database.calls == [(7, 2, 0), (7, 2, 1), (7, 2, 2)]


@pytest.mark.asyncio
async def test_get_model_input_scope_rejects_tampered_or_rebound_cursor() -> None:
    database = FakeDatabase(rows=[scope_row(total=2), scope_row(object_id=12, total=2)])

    async with Client(server(database)) as client:
        first_call = await client.call_tool(
            "get_model_input_scope",
            {"model_id": 7, "page_size": 1},
        )
        first = GetModelInputScopeResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        replacement = "A" if first.next_cursor[0] != "A" else "B"
        tampered = await client.call_tool(
            "get_model_input_scope",
            {
                "model_id": 7,
                "page_size": 1,
                "cursor": f"{replacement}{first.next_cursor[1:]}",
            },
        )
        rebound = await client.call_tool(
            "get_model_input_scope",
            {"model_id": 7, "page_size": 2, "cursor": first.next_cursor},
        )

    assert tampered.is_error is True
    assert rebound.is_error is True
    assert database.calls == [(7, 2, 0)]


@pytest.mark.asyncio
async def test_get_model_input_scope_advertises_bounded_inputs() -> None:
    async with Client(server(FakeDatabase(rows=[]))) as client:
        tools = await client.list_tools()

    schema = next(
        tool.input_schema
        for tool in tools.tools
        if tool.name == "get_model_input_scope"
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
