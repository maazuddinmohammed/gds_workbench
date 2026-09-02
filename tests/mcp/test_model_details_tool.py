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
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
)
from gds_etl_workbench.tools.modeling.model_details import (
    ListModelsResult,
    register_list_models_tool,
)


@dataclass
class FakeDatabase:
    models: list[dict[str, Any]]
    audit_records: list[ToolCallLogRecord] = field(
        default_factory=lambda: list[ToolCallLogRecord]()
    )
    calls: list[tuple[Any, ...]] = field(
        default_factory=lambda: list[tuple[Any, ...]]()
    )
    isolations: list[ReadIsolation] = field(
        default_factory=lambda: list[ReadIsolation]()
    )

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
    ) -> AsyncGenerator[ReadTransaction]:
        self.isolations.append(isolation)
        yield FakeReadTransaction(self)


@dataclass
class FakeReadTransaction:
    database: FakeDatabase

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        raise AssertionError("development mode must not query Principal authorization")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "FROM model.model AS model" in query
        self.database.calls.append(parameters)
        limit, offset = parameters[-2:]
        return self.database.models[offset : offset + limit]


def _server(database: FakeDatabase) -> MCPServer[None]:
    identity = IdentityProvider(AuthMode.DEV)
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-details-test", middleware=[audit])
    register_list_models_tool(
        server,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    return server


def _model(model_id: int = 7) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "model_name": "Northwind",
        "model_description": "Northwind analytics model",
        "model_revision": 4,
        "silver_model_naming_instructions": "Prefix Silver objects with slv_.",
        "silver_model_audit_columns_template": {"columns": ["loaded_at"]},
        "gold_model_naming_instructions": "Prefix Gold objects with gld_.",
        "gold_model_technical_columns_template": {"columns": ["row_hash"]},
        "gold_model_audit_columns_template": {"columns": ["loaded_at"]},
        "model_input_scope_object_count": 12,
        "total_model_count": 1,
    }


@pytest.mark.asyncio
async def test_list_models_returns_headers_and_policy_without_audit_columns() -> None:
    database = FakeDatabase(models=[_model()])

    async with Client(_server(database)) as client:
        call = await client.call_tool("list_models", {"tenant_id": 3})

    result = ListModelsResult.model_validate(call.structured_content)
    assert result.tenant_id == 3
    assert result.model_count == 1
    assert result.models[0].model_name == "Northwind"
    assert (
        result.models[0].silver_model_naming_instructions
        == "Prefix Silver objects with slv_."
    )
    assert "silver_model_naming_template" not in result.models[0].model_dump()
    assert result.models[0].silver_model_audit_columns_template == {
        "columns": ["loaded_at"]
    }
    assert result.models[0].model_input_scope_object_count == 12
    rendered = repr(call.structured_content)
    for forbidden in ("created_time", "created_by", "updated_time", "updated_by"):
        assert forbidden not in rendered
    assert database.calls == [(3, 201, 0)]
    assert database.audit_records[0].input_metadata == {
        "tenant_id": 3,
        "schema_version": "1.0",
        "page_size": 200,
        "cursor_provided": False,
    }


@pytest.mark.asyncio
async def test_list_models_reports_bounded_truncation() -> None:
    models = [_model(model_id) for model_id in range(1, 202)]
    for row in models:
        row["total_model_count"] = 201
    database = FakeDatabase(models=models)

    async with Client(_server(database)) as client:
        call = await client.call_tool("list_models", {"tenant_id": 3})

    result = ListModelsResult.model_validate(call.structured_content)
    assert len(result.models) == 200
    assert result.model_count == 201
    assert result.models_truncated is True


@pytest.mark.asyncio
async def test_list_models_recovers_every_model_across_pages() -> None:
    models = [_model(model_id) for model_id in range(1, 4)]
    for row in models:
        row["total_model_count"] = 3
    database = FakeDatabase(models=models)

    async with Client(_server(database)) as client:
        first_call = await client.call_tool(
            "list_models",
            {"tenant_id": 3, "page_size": 1},
        )
        first = ListModelsResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        second_call = await client.call_tool(
            "list_models",
            {"tenant_id": 3, "page_size": 1, "cursor": first.next_cursor},
        )
        second = ListModelsResult.model_validate(second_call.structured_content)
        assert second.next_cursor is not None
        third_call = await client.call_tool(
            "list_models",
            {"tenant_id": 3, "page_size": 1, "cursor": second.next_cursor},
        )
        third = ListModelsResult.model_validate(third_call.structured_content)

    assert [model.model_id for model in first.models] == [1]
    assert [model.model_id for model in second.models] == [2]
    assert [model.model_id for model in third.models] == [3]
    assert third.next_cursor is None
    assert database.calls == [(3, 2, 0), (3, 2, 1), (3, 2, 2)]


@pytest.mark.asyncio
async def test_list_models_rejects_a_tampered_cursor_before_querying_models() -> None:
    models = [_model(model_id) for model_id in range(1, 3)]
    for row in models:
        row["total_model_count"] = 2
    database = FakeDatabase(models=models)

    async with Client(_server(database)) as client:
        first_call = await client.call_tool(
            "list_models",
            {"tenant_id": 3, "page_size": 1},
        )
        first = ListModelsResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        replacement = "A" if first.next_cursor[0] != "A" else "B"
        rejected = await client.call_tool(
            "list_models",
            {
                "tenant_id": 3,
                "page_size": 1,
                "cursor": f"{replacement}{first.next_cursor[1:]}",
            },
        )

    assert rejected.is_error is True
    assert database.calls == [(3, 2, 0)]


@pytest.mark.asyncio
async def test_list_models_cursor_is_bound_to_tenant_and_page_size() -> None:
    models = [_model(model_id) for model_id in range(1, 3)]
    for row in models:
        row["total_model_count"] = 2
    database = FakeDatabase(models=models)

    async with Client(_server(database)) as client:
        first_call = await client.call_tool(
            "list_models",
            {"tenant_id": 3, "page_size": 1},
        )
        first = ListModelsResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        wrong_tenant = await client.call_tool(
            "list_models",
            {"tenant_id": 4, "page_size": 1, "cursor": first.next_cursor},
        )
        wrong_page_size = await client.call_tool(
            "list_models",
            {"tenant_id": 3, "page_size": 2, "cursor": first.next_cursor},
        )

    assert wrong_tenant.is_error is True
    assert wrong_page_size.is_error is True
    assert database.calls == [(3, 2, 0)]


@pytest.mark.asyncio
async def test_list_models_advertises_bounded_pagination_inputs() -> None:
    async with Client(_server(FakeDatabase(models=[]))) as client:
        tools = await client.list_tools()

    schema = next(
        tool.input_schema for tool in tools.tools if tool.name == "list_models"
    )
    assert schema["properties"]["page_size"] == {
        "default": 200,
        "maximum": 200,
        "minimum": 1,
        "title": "Page Size",
        "type": "integer",
    }
    assert schema["properties"]["cursor"]["anyOf"] == [
        {"maxLength": 2048, "type": "string"},
        {"type": "null"},
    ]
