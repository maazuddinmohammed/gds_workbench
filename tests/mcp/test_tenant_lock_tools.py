from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import TextContent

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
    WriteTransaction,
)
from gds_etl_workbench.tools.tenants.tenant_locks import register_tenant_lock_tools

ENTRA_TENANT_ID = UUID("10000000-0000-0000-0000-000000000021")
ENTRA_OBJECT_ID = UUID("20000000-0000-0000-0000-000000000021")


class StaticIdentityProvider(IdentityProvider):
    def __init__(self) -> None:
        super().__init__(AuthMode.DEV)

    def request_principal(self, request: object | None) -> RequestPrincipal:
        del request
        return RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=ENTRA_TENANT_ID,
            entra_object_id=ENTRA_OBJECT_ID,
        )


class FakeTransaction:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.check_tenant_lock" in query:
            assert parameters == (ENTRA_TENANT_ID, ENTRA_OBJECT_ID, "user", 123)
            return self._database.check_row
        if "security.acquire_tenant_lock" in query:
            assert parameters == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
                90,
                "Edit ingestion metadata",
            )
            return self._database.acquire_row
        if "security.renew_tenant_lock" in query:
            assert parameters == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
                120,
            )
            return self._database.renew_row
        if "security.release_tenant_lock" in query:
            assert parameters == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
            )
            return self._database.release_row
        if "security.override_tenant_lock" in query:
            assert parameters == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
                "Owner is unavailable; approved emergency correction.",
            )
            return self._database.override_row
        if "security.entra_principal_identity" in query:
            return {
                "principal_id": 41,
                "principal_display_name": "Lock Developer",
                "is_super_admin": False,
            }
        raise AssertionError("unexpected query")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        del query, parameters
        raise AssertionError("Tenant Lock tools do not fetch multiple rows")


class FakeDatabase:
    def __init__(
        self,
        check_row: dict[str, Any] | None = None,
        acquire_row: dict[str, Any] | None = None,
        renew_row: dict[str, Any] | None = None,
        release_row: dict[str, Any] | None = None,
        override_row: dict[str, Any] | None = None,
    ) -> None:
        self.check_row = check_row
        self.acquire_row = acquire_row
        self.renew_row = renew_row
        self.release_row = release_row
        self.override_row = override_row
        self.audit_records: list[ToolCallLogRecord] = []
        self.write_transaction_count = 0

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
        assert isolation is ReadIsolation.READ_COMMITTED
        yield FakeTransaction(self)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[WriteTransaction]:
        self.write_transaction_count += 1
        yield FakeTransaction(self)


@pytest.mark.asyncio
async def test_check_tenant_lock_reports_an_unlocked_tenant() -> None:
    database = FakeDatabase(
        {
            "authorized": True,
            "denial_code": None,
            "is_locked": False,
            "owner_display_name": None,
            "owned_by_current_principal": None,
            "purpose": None,
            "acquired_time": None,
            "expires_time": None,
        }
    )
    identity_provider = StaticIdentityProvider()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="tenant-lock-test", middleware=[audit])
    register_tenant_lock_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        audit=audit,
    )

    async with Client(server) as client:
        result = await client.call_tool("check_tenant_lock", {"tenant_id": 123})

    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "is_locked": False,
        "lock": None,
    }
    assert len(database.audit_records) == 1
    assert database.audit_records[0].tool_name == "check_tenant_lock"
    assert database.audit_records[0].status == "succeeded"


@pytest.mark.asyncio
async def test_check_tenant_lock_reports_the_active_owner() -> None:
    acquired_at = datetime(2026, 8, 13, 14, 0, tzinfo=UTC)
    expires_at = datetime(2026, 8, 13, 15, 0, tzinfo=UTC)
    database = FakeDatabase(
        {
            "authorized": True,
            "denial_code": None,
            "is_locked": True,
            "owner_display_name": "Another Developer",
            "owned_by_current_principal": False,
            "purpose": "Update ingestion metadata",
            "acquired_time": acquired_at,
            "expires_time": expires_at,
        }
    )
    identity_provider = StaticIdentityProvider()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="tenant-lock-test", middleware=[audit])
    register_tenant_lock_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        audit=audit,
    )

    async with Client(server) as client:
        result = await client.call_tool("check_tenant_lock", {"tenant_id": 123})

    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "is_locked": True,
        "lock": {
            "owner_display_name": "Another Developer",
            "owned_by_current_principal": False,
            "purpose": "Update ingestion metadata",
            "acquired_at": "2026-08-13T14:00:00Z",
            "expires_at": "2026-08-13T15:00:00Z",
        },
    }
    assert "principal_id" not in str(result.structured_content)


@pytest.mark.asyncio
async def test_acquire_tenant_lock_acquires_an_unlocked_tenant() -> None:
    acquired_at = datetime(2026, 8, 13, 14, 0, tzinfo=UTC)
    expires_at = datetime(2026, 8, 13, 15, 30, tzinfo=UTC)
    database = FakeDatabase(
        acquire_row={
            "acquired": True,
            "denial_code": None,
            "owner_display_name": "Lock Developer",
            "purpose": "Edit ingestion metadata",
            "acquired_time": acquired_at,
            "expires_time": expires_at,
        }
    )
    identity_provider = StaticIdentityProvider()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="tenant-lock-test", middleware=[audit])
    register_tenant_lock_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        audit=audit,
    )

    async with Client(server) as client:
        result = await client.call_tool(
            "acquire_tenant_lock",
            {
                "tenant_id": 123,
                "duration_minutes": 90,
                "purpose": "Edit ingestion metadata",
            },
        )

    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "acquired": True,
        "lock": {
            "owner_display_name": "Lock Developer",
            "owned_by_current_principal": True,
            "purpose": "Edit ingestion metadata",
            "acquired_at": "2026-08-13T14:00:00Z",
            "expires_at": "2026-08-13T15:30:00Z",
        },
    }
    assert database.write_transaction_count == 1
    assert database.audit_records[0].input_metadata == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "duration_minutes": 90,
        "has_purpose": True,
    }


@pytest.mark.asyncio
async def test_acquire_tenant_lock_rejects_an_existing_lock() -> None:
    database = FakeDatabase(
        acquire_row={
            "acquired": False,
            "denial_code": "tenant_locked",
            "owner_display_name": "Another Developer",
            "purpose": "Other work",
            "acquired_time": datetime(2026, 8, 13, 14, 0, tzinfo=UTC),
            "expires_time": datetime(2026, 8, 13, 15, 0, tzinfo=UTC),
        }
    )
    identity_provider = StaticIdentityProvider()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="tenant-lock-test", middleware=[audit])
    register_tenant_lock_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        audit=audit,
    )

    async with Client(server) as client:
        result = await client.call_tool(
            "acquire_tenant_lock",
            {
                "tenant_id": 123,
                "duration_minutes": 90,
                "purpose": "Edit ingestion metadata",
            },
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text.endswith("tenant_locked: Tenant is locked by Another Developer.")


@pytest.mark.asyncio
async def test_renew_tenant_lock_extends_the_current_principals_lock() -> None:
    database = FakeDatabase(
        renew_row={
            "renewed": True,
            "denial_code": None,
            "owner_display_name": "Lock Developer",
            "purpose": "Edit ingestion metadata",
            "acquired_time": datetime(2026, 8, 13, 14, 15, tzinfo=UTC),
            "expires_time": datetime(2026, 8, 13, 16, 15, tzinfo=UTC),
        }
    )
    identity_provider = StaticIdentityProvider()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="tenant-lock-test", middleware=[audit])
    register_tenant_lock_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        audit=audit,
    )

    async with Client(server) as client:
        result = await client.call_tool(
            "renew_tenant_lock",
            {"tenant_id": 123, "duration_minutes": 120},
        )

    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "renewed": True,
        "lock": {
            "owner_display_name": "Lock Developer",
            "owned_by_current_principal": True,
            "purpose": "Edit ingestion metadata",
            "acquired_at": "2026-08-13T14:15:00Z",
            "expires_at": "2026-08-13T16:15:00Z",
        },
    }
    assert database.write_transaction_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("renew_row", "expected_error"),
    [
        (
            {
                "renewed": False,
                "denial_code": "tenant_lock_required",
                "owner_display_name": None,
                "purpose": None,
                "acquired_time": None,
                "expires_time": None,
            },
            "tenant_lock_required: An active Tenant Lock owned by the current "
            "Principal is required.",
        ),
        (
            {
                "renewed": False,
                "denial_code": "tenant_locked",
                "owner_display_name": "Another Developer",
                "purpose": "Other work",
                "acquired_time": datetime(2026, 8, 13, 14, 0, tzinfo=UTC),
                "expires_time": datetime(2026, 8, 13, 15, 0, tzinfo=UTC),
            },
            "tenant_locked: Tenant is locked by Another Developer.",
        ),
    ],
)
async def test_renew_tenant_lock_rejects_missing_or_other_owned_lock(
    renew_row: dict[str, Any],
    expected_error: str,
) -> None:
    database = FakeDatabase(renew_row=renew_row)
    identity_provider = StaticIdentityProvider()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="tenant-lock-test", middleware=[audit])
    register_tenant_lock_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        audit=audit,
    )

    async with Client(server) as client:
        result = await client.call_tool(
            "renew_tenant_lock",
            {"tenant_id": 123, "duration_minutes": 120},
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text.endswith(expected_error)


@pytest.mark.asyncio
async def test_release_tenant_lock_releases_the_current_principals_lock() -> None:
    database = FakeDatabase(
        release_row={
            "released": True,
            "denial_code": None,
            "owner_display_name": "Lock Developer",
            "acquired_time": datetime(2026, 8, 13, 14, 0, tzinfo=UTC),
            "expires_time": datetime(2026, 8, 13, 15, 0, tzinfo=UTC),
        }
    )
    identity_provider = StaticIdentityProvider()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="tenant-lock-test", middleware=[audit])
    register_tenant_lock_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        audit=audit,
    )

    async with Client(server) as client:
        result = await client.call_tool("release_tenant_lock", {"tenant_id": 123})

    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "released": True,
        "is_locked": False,
    }
    assert database.write_transaction_count == 1


@pytest.mark.asyncio
async def test_override_tenant_lock_releases_another_principals_lock_only() -> None:
    database = FakeDatabase(
        override_row={
            "overridden": True,
            "denial_code": None,
            "previous_owner_display_name": "Another Developer",
            "previous_owned_by_current_principal": False,
            "previous_purpose": "Other work",
            "previous_acquired_time": datetime(2026, 8, 13, 14, 0, tzinfo=UTC),
            "previous_expires_time": datetime(2026, 8, 13, 15, 0, tzinfo=UTC),
        }
    )
    identity_provider = StaticIdentityProvider()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="tenant-lock-test", middleware=[audit])
    register_tenant_lock_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        audit=audit,
    )
    reason = "Owner is unavailable; approved emergency correction."

    async with Client(server) as client:
        result = await client.call_tool(
            "override_tenant_lock",
            {"tenant_id": 123, "reason": reason},
        )

    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "overridden": True,
        "is_locked": False,
        "previous_lock": {
            "owner_display_name": "Another Developer",
            "owned_by_current_principal": False,
            "purpose": "Other work",
            "acquired_at": "2026-08-13T14:00:00Z",
            "expires_at": "2026-08-13T15:00:00Z",
        },
    }
    assert database.write_transaction_count == 1
    assert reason not in str(database.audit_records[0].input_metadata)
    assert database.audit_records[0].input_metadata == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "has_reason": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override_row", "expected_error"),
    [
        (
            {
                "overridden": False,
                "denial_code": "tenant_lock_required",
                "previous_owner_display_name": None,
                "previous_owned_by_current_principal": None,
                "previous_purpose": None,
                "previous_acquired_time": None,
                "previous_expires_time": None,
            },
            "invalid_request: Tenant is not currently locked.",
        ),
        (
            {
                "overridden": False,
                "denial_code": "tenant_locked",
                "previous_owner_display_name": "Lock Developer",
                "previous_owned_by_current_principal": True,
                "previous_purpose": "Current work",
                "previous_acquired_time": datetime(2026, 8, 13, 14, 0, tzinfo=UTC),
                "previous_expires_time": datetime(2026, 8, 13, 15, 0, tzinfo=UTC),
            },
            "invalid_request: The current Principal owns this Tenant Lock; use "
            "release_tenant_lock.",
        ),
    ],
)
async def test_override_tenant_lock_rejects_missing_or_current_owned_lock(
    override_row: dict[str, Any],
    expected_error: str,
) -> None:
    database = FakeDatabase(override_row=override_row)
    identity_provider = StaticIdentityProvider()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="tenant-lock-test", middleware=[audit])
    register_tenant_lock_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        audit=audit,
    )

    async with Client(server) as client:
        result = await client.call_tool(
            "override_tenant_lock",
            {
                "tenant_id": 123,
                "reason": "Owner is unavailable; approved emergency correction.",
            },
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text.endswith(expected_error)
