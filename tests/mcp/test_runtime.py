from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any, LiteralString

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from starlette.testclient import TestClient

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.server import create_mcp_server
from gds_etl_workbench.configuration import AuthMode, Environment, RuntimeSettings
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadTransaction,
    ToolCallLogRecord,
)
from gds_etl_workbench.runtime import (
    create_application,
    create_application_from_environment,
)


class FakeReadTransaction:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    async def fetch_one(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> dict[str, Any] | None:
        if self._database.resolved_principal is None:
            raise AssertionError(
                "development mode must not resolve a production Principal"
            )
        return self._database.resolved_principal

    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        limit, offset = parameters[-2:]
        return self._database.records[offset : offset + limit]


class FakeDatabase:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.opened = False
        self.closed = False
        self.expiry_calls = 0
        self.audit_unavailable = False
        self.audit_records: list[ToolCallLogRecord] = []
        self.resolved_principal: dict[str, Any] | None = None
        self.records: list[dict[str, Any]] = [
            {
                "tenant_id": 1,
                "tenant_code": "T1",
                "tenant_name": "Tenant One",
                "tenant_description": None,
                "tenant_visibility": "private",
                "effective_role": "development",
            }
        ]

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    async def readiness(self) -> ReadinessRecord:
        return ReadinessRecord(
            ready=self.ready,
            code="ready" if self.ready else "database_unavailable",
        )

    async def expire_tenant_locks(self) -> int:
        self.expiry_calls += 1
        return 0

    async def append_tool_call_log(self, record: ToolCallLogRecord) -> None:
        if self.audit_unavailable:
            raise DependencyUnavailableError()
        self.audit_records.append(record)

    @asynccontextmanager
    async def read_transaction(self) -> AsyncIterator[ReadTransaction]:
        yield FakeReadTransaction(self)


def development_settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_ENVIRONMENT": "local",
            "GDS_AUTH_MODE": "dev",
            "GDS_DATABASE_DSN": "postgresql://app@db.example.invalid/workbench",
            "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_MCP_ALLOWED_HOSTS": "testserver,testserver:*",
            "GDS_REQUIRE_HTTPS": "false",
            "GDS_SCHEMA_VERSION": "1.0.0",
            "GDS_DATABASE_POOL_MIN": "1",
            "GDS_DATABASE_POOL_MAX": "5",
            "GDS_DATABASE_POOL_TIMEOUT_SECONDS": "10",
            "GDS_DATABASE_CONNECTION_BUDGET": "100",
            "GDS_DATABASE_CONNECTION_HEADROOM": "20",
            "GDS_REQUEST_TIMEOUT_SECONDS": "120",
            "WEB_CONCURRENCY": "2",
            "PORT": "8000",
        }
    )


@pytest.mark.asyncio
async def test_mcp_inventory_and_list_tenants_tool() -> None:
    settings = development_settings()
    database = FakeDatabase()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        tools = await client.list_tools()
        result = await client.call_tool("list_tenants", {"page_size": 50})

    assert [tool.name for tool in tools.tools] == ["list_tenants"]
    assert tools.tools[0].meta == {"gds/toolPolicy": "tenant_read"}
    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "tenants": [
            {
                "tenant_id": 1,
                "tenant_code": "T1",
                "tenant_name": "Tenant One",
                "tenant_description": None,
                "tenant_visibility": "private",
                "effective_role": "development",
            }
        ],
        "next_cursor": None,
    }
    assert database.opened is True
    assert database.closed is True
    assert len(database.audit_records) == 1
    assert database.audit_records[0].principal_display_name == "Local Developer"
    assert database.audit_records[0].status == "succeeded"


@pytest.mark.asyncio
async def test_server_expires_tenant_locks_during_lifespan() -> None:
    settings = development_settings()
    database = FakeDatabase()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server):
        pass

    assert database.expiry_calls == 1


@pytest.mark.asyncio
async def test_tool_call_fails_safely_when_required_audit_is_unavailable() -> None:
    settings = development_settings()
    database = FakeDatabase()
    database.audit_unavailable = True
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        with pytest.raises(MCPError, match="Tool-call audit is unavailable"):
            await client.call_tool("list_tenants", {})

    assert database.audit_records == []


def test_health_routes_are_anonymous() -> None:
    database = FakeDatabase()
    application = create_application(development_settings(), database)

    with TestClient(application) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_production_mcp_rejects_missing_easy_auth_envelope() -> None:
    settings = replace(
        development_settings(),
        environment=Environment.PRODUCTION,
        auth_mode=AuthMode.AZURE_EASY_AUTH,
        require_https=True,
    )
    application = create_application(settings, FakeDatabase())

    with TestClient(application) as client:
        response = client.post("/mcp", headers={"x-forwarded-proto": "https"}, json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


@pytest.mark.asyncio
async def test_easy_auth_principal_reaches_list_tenants_over_stateless_http() -> None:
    settings = replace(
        development_settings(),
        environment=Environment.PRODUCTION,
        auth_mode=AuthMode.AZURE_EASY_AUTH,
        require_https=True,
    )
    database = FakeDatabase()
    database.resolved_principal = {
        "principal_id": 41,
        "principal_display_name": "HTTP Human",
        "is_super_admin": False,
    }
    database.records[0]["tenant_visibility"] = "global"
    database.records[0]["effective_role"] = "viewer"
    application = create_application(settings, database)
    claims = {
        "auth_typ": "aad",
        "claims": [
            {"typ": "tid", "val": "11111111-1111-1111-1111-111111111111"},
            {"typ": "oid", "val": "22222222-2222-2222-2222-222222222222"},
            {"typ": "idtyp", "val": "user"},
            {"typ": "scp", "val": "workbench.access"},
        ],
    }
    principal_header = base64.b64encode(json.dumps(claims).encode()).decode()

    async with (
        application.router.lifespan_context(application),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=application),
            base_url="http://testserver",
            headers={
                "x-forwarded-proto": "https",
                "x-ms-client-principal": principal_header,
            },
        ) as http_client,
    ):
        transport = streamable_http_client(
            "http://testserver/mcp",
            http_client=http_client,
            terminate_on_close=False,
        )
        async with Client(transport) as client:
            result = await client.call_tool("list_tenants", {})

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["tenants"][0]["effective_role"] == "viewer"
    assert len(database.audit_records) == 1
    assert database.audit_records[0].principal_id == 41
    assert database.audit_records[0].principal_display_name == "HTTP Human"


def test_invalid_configuration_preserves_only_safe_health_behavior() -> None:
    application = create_application_from_environment({})

    with TestClient(application) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        mcp = client.post("/mcp", json={})

    assert live.status_code == 200
    assert ready.status_code == 503
    assert mcp.status_code == 503
    assert "GDS_" not in ready.text
