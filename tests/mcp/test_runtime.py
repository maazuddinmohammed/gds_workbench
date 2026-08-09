from __future__ import annotations

from dataclasses import replace

import pytest
from mcp import Client
from starlette.testclient import TestClient

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.server import create_mcp_server
from gds_etl_workbench.application.ports import ReadinessRecord, TenantRecord
from gds_etl_workbench.configuration import AuthMode, Environment, RuntimeSettings
from gds_etl_workbench.domain.authorization import RequestPrincipal, TenantRole
from gds_etl_workbench.runtime import (
    create_application,
    create_application_from_environment,
)


class FakeRepository:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.opened = False
        self.closed = False

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    async def readiness(self) -> ReadinessRecord:
        return ReadinessRecord(
            ready=self.ready,
            code="ready" if self.ready else "database_unavailable",
        )

    async def list_tenants(
        self, principal: RequestPrincipal, *, limit: int, offset: int
    ) -> list[TenantRecord]:
        assert principal == RequestPrincipal.development()
        records = [
            TenantRecord(
                tenant_id=1,
                tenant_code="T1",
                tenant_name="Tenant One",
                tenant_description=None,
                tenant_visibility="private",
                effective_role=TenantRole.DEVELOPMENT,
            )
        ]
        return records[offset : offset + limit]


def development_settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_ENVIRONMENT": "development",
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
    repository = FakeRepository()
    server = create_mcp_server(
        settings, repository, IdentityProvider(settings.auth_mode)
    )

    async with Client(server) as client:
        tools = await client.list_tools()
        result = await client.call_tool("list_tenants", {"page_size": 50})

    assert [tool.name for tool in tools.tools] == ["list_tenants"]
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
    assert repository.opened is True
    assert repository.closed is True


def test_health_routes_are_anonymous() -> None:
    repository = FakeRepository()
    application = create_application(development_settings(), repository)

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
    application = create_application(settings, FakeRepository())

    with TestClient(application) as client:
        response = client.post("/mcp", headers={"x-forwarded-proto": "https"}, json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


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
