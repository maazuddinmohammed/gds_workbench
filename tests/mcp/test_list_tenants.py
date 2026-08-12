from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, LiteralString

import pytest
from mcp import Client

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.server import create_mcp_server
from gds_etl_workbench.configuration import RuntimeSettings
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
)
from gds_etl_workbench.tools.tenants.list_tenants import ListTenantsResult


@dataclass
class RecordingDatabase:
    records: list[dict[str, Any]]
    calls: list[tuple[int, int]] = field(default_factory=list)
    isolations: list[ReadIsolation] = field(default_factory=list)
    audit_records: list[ToolCallLogRecord] = field(default_factory=list)

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
        yield RecordingReadTransaction(self)


@dataclass
class RecordingReadTransaction:
    database: RecordingDatabase

    async def fetch_one(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> dict[str, Any] | None:
        raise AssertionError("development mode must not resolve a production Principal")

    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        limit, offset = parameters[-2:]
        self.database.calls.append((limit, offset))
        return self.database.records[offset : offset + limit]


def settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_ENVIRONMENT": "local",
            "GDS_DATABASE_DSN": "postgresql://app@db.example.invalid/workbench",
            "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_MCP_PUBLIC_URL": "https://testserver/mcp",
            "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": (
                "https://snapshot.blob.core.windows.net"
            ),
            "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
        }
    )


def tenant(tenant_id: int, name: str) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "tenant_code": f"T{tenant_id}",
        "tenant_name": name,
        "tenant_description": None,
        "tenant_visibility": "private",
        "effective_role": "development",
    }


@pytest.mark.asyncio
async def test_list_tenants_pages_with_a_signed_cursor() -> None:
    database = RecordingDatabase([tenant(1, "Alpha"), tenant(2, "Beta")])
    runtime_settings = settings()
    server = create_mcp_server(
        runtime_settings,
        database,
        IdentityProvider(runtime_settings.auth_mode),
    )

    async with Client(server) as client:
        first_call = await client.call_tool("list_tenants", {"page_size": 1})
        first = ListTenantsResult.model_validate(first_call.structured_content)
        second_call = await client.call_tool(
            "list_tenants",
            {"page_size": 1, "cursor": first.next_cursor},
        )
        second = ListTenantsResult.model_validate(second_call.structured_content)

    assert [item.tenant_name for item in first.tenants] == ["Alpha"]
    assert [item.tenant_name for item in second.tenants] == ["Beta"]
    assert second.next_cursor is None
    assert database.calls == [(2, 0), (2, 1)]
    assert database.isolations == [
        ReadIsolation.READ_COMMITTED,
        ReadIsolation.REPEATABLE_READ,
        ReadIsolation.READ_COMMITTED,
        ReadIsolation.REPEATABLE_READ,
    ]
    assert [record.status for record in database.audit_records] == [
        "succeeded",
        "succeeded",
    ]
    assert database.audit_records[0].input_metadata == {
        "schema_version": "1.0",
        "page_size": 1,
        "cursor_provided": False,
    }
    assert database.audit_records[1].input_metadata["cursor_provided"] is True


@pytest.mark.asyncio
async def test_tampered_cursor_is_rejected_before_database_access() -> None:
    database = RecordingDatabase([tenant(1, "Alpha"), tenant(2, "Beta")])
    runtime_settings = settings()
    server = create_mcp_server(
        runtime_settings,
        database,
        IdentityProvider(runtime_settings.auth_mode),
    )

    async with Client(server) as client:
        first_call = await client.call_tool("list_tenants", {"page_size": 1})
        first = ListTenantsResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        replacement = "A" if first.next_cursor[0] != "A" else "B"
        tampered = f"{replacement}{first.next_cursor[1:]}"
        rejected = await client.call_tool(
            "list_tenants",
            {"page_size": 1, "cursor": tampered},
        )

    assert rejected.is_error is True
    assert database.calls == [(2, 0)]
    assert database.audit_records[-1].status == "failed"
    assert database.audit_records[-1].failure_code == "tool_error"
    assert database.audit_records[-1].input_metadata == {
        "schema_version": "1.0",
        "page_size": 1,
        "cursor_provided": True,
    }
