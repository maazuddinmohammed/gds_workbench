from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import Decimal
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
from gds_etl_workbench.tools.modeling.profiling_analysis import (
    GetModelAnalysisResult,
    GetModelProfilingResult,
    register_profiling_analysis_tools,
)


@dataclass
class FakeDatabase:
    profiles: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    audit_records: list[ToolCallLogRecord] = field(default_factory=list)
    isolations: list[ReadIsolation] = field(default_factory=list)

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
        if "FROM model.model\n" in query:
            assert parameters == (7,)
            return {
                "model_id": 7,
                "tenant_id": 3,
                "model_name": "Northwind",
                "model_revision": 4,
            }
        if "FROM model.model_scope" in query:
            return {"object_count": len(parameters[1])}
        raise AssertionError("unexpected query")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        limit, offset = parameters[-2:]
        rows = (
            self.database.profiles
            if "workflow.attribute_profile" in query
            else self.database.relationships
        )
        return rows[offset : offset + limit]


def _server(database: FakeDatabase) -> MCPServer[None]:
    identity = IdentityProvider(AuthMode.DEV)
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="modeling-read-test", middleware=[audit])
    register_profiling_analysis_tools(
        server,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    return server


def _profile() -> dict[str, Any]:
    return {
        "object_id": 11,
        "tenant_code": "northwind",
        "system_code": "erp",
        "connection_code": "source",
        "object_schema": "sales",
        "object_name": "orders",
        "attribute_id": 12,
        "attribute_name": "customer_id",
        "row_count": 100,
        "non_null_count": 90,
        "null_count": 10,
        "blank_count": 0,
        "distinct_count": 45,
        "min_data_length": 1,
        "max_data_length": 10,
        "avg_data_length": Decimal("5.5"),
        "percent_populated": Decimal("90"),
        "percent_duplicates": Decimal("50"),
        "percent_null": Decimal("10"),
        "percent_blank": Decimal("0"),
        "percent_distinct": Decimal("50"),
    }


def _relationship() -> dict[str, Any]:
    return {
        "from_object_id": 11,
        "from_tenant_code": "northwind",
        "from_system_code": "erp",
        "from_connection_code": "source",
        "from_object_schema": "sales",
        "from_object_name": "orders",
        "from_attribute_id": 12,
        "from_attribute_name": "customer_id",
        "to_object_id": 21,
        "to_tenant_code": "northwind",
        "to_system_code": "erp",
        "to_connection_code": "source",
        "to_object_schema": "sales",
        "to_object_name": "customers",
        "to_attribute_id": 22,
        "to_attribute_name": "customer_id",
        "relationship_kind": "foreign_key_candidate",
        "relationship_confidence": "high",
        "relationship_basis": "All source values match a unique target value.",
        "validation_policy_version": "1.0.0",
        "validation_result": "supported",
        "validation_source_non_null_count": 90,
        "validation_source_distinct_count": 45,
        "validation_target_non_null_count": 50,
        "validation_target_distinct_count": 50,
        "validation_source_missing_target_count": 0,
        "validation_unused_target_count": 5,
        "validation_duplicate_target_key_count": 0,
        "analysis_result_status": "active",
        "analysis_result_is_locked": False,
    }


@pytest.mark.asyncio
async def test_profiling_expands_names_and_omits_internal_columns() -> None:
    database = FakeDatabase(profiles=[_profile()])

    async with Client(_server(database)) as client:
        call = await client.call_tool(
            "get_model_profiling",
            {"model_id": 7, "object_ids": [11]},
        )

    result = GetModelProfilingResult.model_validate(call.structured_content)
    assert result.profiles[0].object_name == "orders"
    assert result.profiles[0].attribute_name == "customer_id"
    rendered = repr(call.structured_content)
    for forbidden in (
        "agent_run_id",
        "source_context_digest",
        "created_by",
        "updated_by",
        "created_time",
        "updated_time",
    ):
        assert forbidden not in rendered
    assert database.audit_records[0].input_metadata["object_count"] == 1


@pytest.mark.asyncio
async def test_analysis_returns_selected_object_on_both_relationship_sides() -> None:
    database = FakeDatabase(relationships=[_relationship()])

    async with Client(_server(database)) as client:
        from_call = await client.call_tool(
            "get_model_analysis",
            {"model_id": 7, "object_ids": [11]},
        )
        to_call = await client.call_tool(
            "get_model_analysis",
            {"model_id": 7, "object_ids": [21]},
        )

    from_result = GetModelAnalysisResult.model_validate(from_call.structured_content)
    to_result = GetModelAnalysisResult.model_validate(to_call.structured_content)
    assert len(from_result.from_relationships) == 1
    assert from_result.to_relationships == ()
    assert to_result.from_relationships == ()
    assert len(to_result.to_relationships) == 1
    assert to_result.to_relationships[0].to_object_name == "customers"


@pytest.mark.asyncio
async def test_empty_analysis_filter_returns_complete_directional_views() -> None:
    database = FakeDatabase(relationships=[_relationship()])

    async with Client(_server(database)) as client:
        call = await client.call_tool("get_model_analysis", {"model_id": 7})

    result = GetModelAnalysisResult.model_validate(call.structured_content)
    assert len(result.from_relationships) == 1
    assert len(result.to_relationships) == 1
