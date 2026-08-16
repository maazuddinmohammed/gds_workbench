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
from gds_etl_workbench.tools.modeling.model_details import (
    GetModelResult,
    register_get_model_tool,
)


@dataclass
class FakeDatabase:
    models: list[dict[str, Any]]
    audit_records: list[ToolCallLogRecord] = field(default_factory=list)
    calls: list[tuple[Any, ...]] = field(default_factory=list)
    isolations: list[ReadIsolation] = field(default_factory=list)

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
        return self.database.models[: parameters[-1]]


def _server(database: FakeDatabase) -> MCPServer[None]:
    identity = IdentityProvider(AuthMode.DEV)
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="model-details-test", middleware=[audit])
    register_get_model_tool(
        server,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
    )
    return server


def _model(model_id: int = 7) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "model_name": "Northwind",
        "model_description": "Northwind analytics model",
        "model_revision": 4,
        "silver_model_naming_template": {"prefix": "slv"},
        "silver_model_audit_columns_template": {"columns": ["loaded_at"]},
        "gold_model_naming_template": {"prefix": "gld"},
        "gold_model_technical_columns_template": {"columns": ["row_hash"]},
        "gold_model_audit_columns_template": {"columns": ["loaded_at"]},
        "model_scope_object_count": 12,
        "total_model_count": 1,
    }


@pytest.mark.asyncio
async def test_get_model_returns_headers_and_policy_without_audit_columns() -> None:
    database = FakeDatabase(models=[_model()])

    async with Client(_server(database)) as client:
        call = await client.call_tool("get_model", {"tenant_id": 3})

    result = GetModelResult.model_validate(call.structured_content)
    assert result.tenant_id == 3
    assert result.model_count == 1
    assert result.models[0].model_name == "Northwind"
    assert result.models[0].silver_model_audit_columns_template == {
        "columns": ["loaded_at"]
    }
    assert result.models[0].model_scope_object_count == 12
    rendered = repr(call.structured_content)
    for forbidden in ("created_time", "created_by", "updated_time", "updated_by"):
        assert forbidden not in rendered
    assert database.calls == [(3, 201)]
    assert database.audit_records[0].input_metadata == {
        "tenant_id": 3,
        "schema_version": "1.0",
    }


@pytest.mark.asyncio
async def test_get_model_reports_bounded_truncation() -> None:
    models = [_model(model_id) for model_id in range(1, 202)]
    for row in models:
        row["total_model_count"] = 201
    database = FakeDatabase(models=models)

    async with Client(_server(database)) as client:
        call = await client.call_tool("get_model", {"tenant_id": 3})

    result = GetModelResult.model_validate(call.structured_content)
    assert len(result.models) == 200
    assert result.model_count == 201
    assert result.models_truncated is True
