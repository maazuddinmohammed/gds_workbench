from __future__ import annotations

import base64
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, LiteralString
from uuid import UUID

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
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
    WriteTransaction,
)
from gds_etl_workbench.runtime import (
    create_application,
    create_application_from_environment,
)
from gds_etl_workbench.tools.snapshots.metadata import (
    get_metadata_snapshot as metadata_snapshot_module,
)
from gds_etl_workbench.tools.snapshots.metadata.archive import (
    SnapshotArchive,
    build_dataset_document,
)
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS_BY_NAME
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    ReadyMetadataSnapshot,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres


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
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        assert isolation in {
            ReadIsolation.READ_COMMITTED,
            ReadIsolation.REPEATABLE_READ,
        }
        yield FakeReadTransaction(self)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[WriteTransaction]:
        yield FakeReadTransaction(self)


class FakeSnapshotStore:
    def __init__(
        self,
        read_url: str = (
            "https://snapshot.blob.core.windows.net/snapshots/metadata/123/"
            "7d7cc8ad-62b5-44ef-aeb0-c09c770ff233.zip?sp=r&sig=fake"
        ),
    ) -> None:
        self.closed = False
        self.read_url = read_url
        self.read_url_calls: list[tuple[int, UUID, datetime, int]] = []

    async def close(self) -> None:
        self.closed = True

    async def upload_archive(
        self,
        archive: SnapshotArchive,
        *,
        snapshot_kind: str,
        scope_id: int,
        schema_version: str,
        snapshot_id: UUID,
        created_at: datetime,
        available_until: datetime,
    ) -> None:
        raise AssertionError(
            "tool orchestration is replaced in this HTTP contract test"
        )

    async def create_read_url(
        self,
        *,
        snapshot_kind: str,
        scope_id: int,
        schema_version: str,
        snapshot_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> str | None:
        assert snapshot_kind == "metadata"
        assert schema_version == "2.0"
        self.read_url_calls.append((scope_id, snapshot_id, now, ttl_seconds))
        return self.read_url


def development_settings() -> RuntimeSettings:
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


@pytest.mark.asyncio
async def test_mcp_inventory_and_list_tenants_tool() -> None:
    settings = development_settings()
    database = FakeDatabase()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        tools = await client.list_tools()
        result = await client.call_tool("list_tenants", {"page_size": 50})

    assert [tool.name for tool in tools.tools] == [
        "list_tenants",
        "get_tenant_details",
        "get_model",
        "get_model_scope",
        "check_tenant_lock",
        "acquire_tenant_lock",
        "renew_tenant_lock",
        "release_tenant_lock",
        "override_tenant_lock",
        "create_metadata_change_set",
        "stage_metadata_change_set",
        "get_metadata_change_set",
        "validate_metadata_change_set",
        "apply_metadata_change_set",
        "archive_metadata_change_set",
        "create_model_change_set",
        "stage_model_change_set",
        "get_model_change_set",
        "validate_model_change_set",
        "apply_model_change_set",
        "archive_model_change_set",
        "list_objects",
        "get_objects",
        "get_object_lineage",
        "list_copy_groups",
        "get_copy_group",
        "list_process_groups",
        "get_process_group",
        "get_model_profiling",
        "get_model_analysis",
        "get_modeling_assertion_documents",
        "get_modeling_assertion_records",
        "get_model_conceptual_objects",
        "get_model_conceptual_relationships",
        "get_model_logical_submodels",
        "get_model_logical_entities",
        "get_model_logical_attributes",
        "get_model_logical_relationships",
        "get_model_dimensional_submodels",
        "get_model_dimensional_entities",
        "get_model_dimensional_attributes",
        "get_model_dimensional_relationships",
        "get_model_mapping_dependencies",
        "get_model_object_mappings",
        "get_model_attribute_mappings",
        "execute_databricks_sql",
        "describe_model_dataset",
        "get_model_snapshot",
        "get_model_dbml",
        "describe_metadata_dataset",
        "get_metadata_snapshot",
    ]
    tools_by_name = {tool.name: tool for tool in tools.tools}
    assert tools_by_name["validate_model_change_set"].annotations is not None
    assert (
        tools_by_name["validate_model_change_set"].annotations.idempotent_hint
        is False
    )
    assert tools_by_name["apply_model_change_set"].annotations is not None
    assert tools_by_name["apply_model_change_set"].annotations.destructive_hint is True
    assert tools_by_name["archive_model_change_set"].annotations is not None
    assert tools_by_name["archive_model_change_set"].annotations.destructive_hint is True
    assert tools_by_name["get_model_snapshot"].annotations is not None
    assert tools_by_name["get_model_snapshot"].annotations.idempotent_hint is False
    assert tools_by_name["get_model_dbml"].annotations is not None
    assert tools_by_name["get_model_dbml"].annotations.idempotent_hint is False
    assert all(
        tool.meta
        == {
            "gds/toolPolicy": (
                "tenant_metadata_write"
                if tool.name
                in {
                    "create_metadata_change_set",
                    "stage_metadata_change_set",
                    "validate_metadata_change_set",
                    "apply_metadata_change_set",
                }
                else "tenant_model_write"
                if tool.name
                in {
                    "create_model_change_set",
                    "stage_model_change_set",
                    "validate_model_change_set",
                    "apply_model_change_set",
                }
                else "tenant_lock_manage"
                if "tenant_lock" in tool.name
                or tool.name
                in {
                    "get_metadata_change_set",
                    "archive_metadata_change_set",
                }
                else "tenant_read"
            )
        }
        for tool in tools.tools
    )
    output_schemas = json.dumps([tool.output_schema for tool in tools.tools])
    for forbidden_field in ("created_time", "created_by", "updated_time", "updated_by"):
        assert f'"{forbidden_field}"' not in output_schemas
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
async def test_describe_metadata_dataset_returns_the_exact_generated_contract() -> None:
    settings = development_settings()
    database = FakeDatabase()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        result = await client.call_tool(
            "describe_metadata_dataset",
            {"dataset": "copy_group"},
        )

    assert result.is_error is False
    assert result.structured_content is not None
    dataset_schema = build_dataset_document(DATASETS_BY_NAME["copy_group"]).schema
    assert result.structured_content == {
        "schema_version": "1.0",
        "dataset": "copy_group",
        "record_type": "copy_group",
        "section": "operational",
        "change_set_eligible": True,
        "natural_key": ["tenant_code", "system_code", "copy_group_name"],
        "references": [
            {
                "columns": ["tenant_code"],
                "target_record_type": "tenant",
                "target_columns": ["tenant_code"],
                "nullable": False,
            },
            {
                "columns": ["system_code"],
                "target_record_type": "system",
                "target_columns": ["system_code"],
                "nullable": False,
            },
        ],
        "dependencies": [
            {"record_type": "tenant", "datasets": ["tenant"]},
            {"record_type": "system", "datasets": ["system"]},
        ],
        "population_rules": dataset_schema["x-gds-population-rules"],
        "columns": dataset_schema["x-gds-columns"],
        "dataset_schema": dataset_schema,
    }
    assert database.audit_records[0].input_metadata == {
        "schema_version": "1.0",
        "dataset": "copy_group",
    }


@pytest.mark.asyncio
async def test_get_metadata_snapshot_returns_only_bounded_descriptor_over_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_id = UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233")
    created_at = datetime.now(UTC)
    database = FakeDatabase()
    store = FakeSnapshotStore()

    async def fake_create_metadata_snapshot(
        *_args: Any, **kwargs: Any
    ) -> ReadyMetadataSnapshot:
        assert kwargs["tenant_id"] == 123
        return ReadyMetadataSnapshot(
            snapshot_id=snapshot_id,
            tenant_id=123,
            created_at=created_at,
            available_until=created_at + timedelta(hours=24),
            size_bytes=4567,
            sha256="a" * 64,
        )

    monkeypatch.setattr(
        metadata_snapshot_module,
        "create_metadata_snapshot",
        fake_create_metadata_snapshot,
    )
    application = create_application(development_settings(), database, store)

    async with (
        application.router.lifespan_context(application),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=application),
            base_url="http://testserver",
        ) as http_client,
    ):
        transport = streamable_http_client(
            "http://testserver/mcp",
            http_client=http_client,
            terminate_on_close=False,
        )
        async with Client(transport) as client:
            result = await client.call_tool(
                "get_metadata_snapshot",
                {"tenant_id": 123},
            )

    assert result.is_error is False
    assert result.structured_content is not None
    descriptor = dict(result.structured_content)
    download_available_until = datetime.fromisoformat(
        descriptor.pop("download_url_expires_at").replace("Z", "+00:00")
    )
    assert descriptor == {
        "schema_version": "2.0",
        "snapshot_id": str(snapshot_id),
        "snapshot_kind": "metadata",
        "status": "ready",
        "tenant_id": 123,
        "download_url": store.read_url,
        "size_bytes": 4567,
        "sha256": "a" * 64,
        "content_type": "application/zip",
    }
    assert set(result.structured_content) == {
        "schema_version",
        "snapshot_id",
        "snapshot_kind",
        "status",
        "tenant_id",
        "download_url",
        "download_url_expires_at",
        "size_bytes",
        "sha256",
        "content_type",
    }
    assert len(database.audit_records) == 1
    assert database.audit_records[0].tool_name == "get_metadata_snapshot"
    assert database.audit_records[0].tenant_id == 123
    assert database.audit_records[0].input_metadata == {
        "schema_version": "2.0",
        "tenant_id": 123,
    }
    assert store.closed is True
    assert len(store.read_url_calls) == 1
    assert store.read_url_calls[0][0:2] == (123, snapshot_id)
    assert store.read_url_calls[0][3] == 900
    assert download_available_until == store.read_url_calls[0][2] + timedelta(
        seconds=900
    )


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


def test_oauth_protected_resource_metadata_is_anonymous_and_configured() -> None:
    settings = replace(
        development_settings(),
        environment=Environment.PRODUCTION,
        auth_mode=AuthMode.AZURE_EASY_AUTH,
        require_https=True,
    )
    application = create_application(settings, FakeDatabase())
    expected = {
        "resource": "https://testserver/mcp",
        "authorization_servers": [
            "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0"
        ],
        "scopes_supported": ["https://testserver/mcp/workbench.access"],
        "bearer_methods_supported": ["header"],
    }

    with TestClient(application) as client:
        root_metadata = client.get("/.well-known/oauth-protected-resource")
        mcp_metadata = client.get("/.well-known/oauth-protected-resource/mcp")

    for response in (root_metadata, mcp_metadata):
        assert response.status_code == 200
        assert response.json() == expected
        assert response.headers["cache-control"] == "public, max-age=300"


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


@pytest.mark.asyncio
async def test_easy_auth_list_tenants_uses_the_production_postgres_path(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000021")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000021")
    with postgres_database.connect_owner() as connection:
        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES ('HTTP_RUNTIME', 'HTTP Runtime Project')
            RETURNING project_id
            """
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog,
                tenant_visibility
            )
            VALUES (%s, 'HTTP_RUNTIME', 'HTTP Runtime Tenant',
                    'http_runtime', 'http_runtime_admin', 'private')
            RETURNING tenant_id
            """,
            (project["project_id"],),
        ).fetchone()
        assert tenant is not None
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            )
            VALUES ('user', 'HTTP Runtime Human', 'http.runtime@example.test')
            RETURNING principal_id
            """
        ).fetchone()
        assert principal is not None
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            )
            VALUES (%s, 'user', %s, %s)
            """,
            (principal["principal_id"], entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            )
            VALUES (%s, %s, 'viewer', %s)
            """,
            (
                tenant["tenant_id"],
                principal["principal_id"],
                principal["principal_id"],
            ),
        )

    settings = replace(
        development_settings(),
        environment=Environment.PRODUCTION,
        auth_mode=AuthMode.AZURE_EASY_AUTH,
        require_https=True,
    )
    database = postgres_database.create_runtime_adapter()
    application = create_application(settings, database, FakeSnapshotStore())
    claims = {
        "auth_typ": "aad",
        "claims": [
            {"typ": "tid", "val": str(entra_tenant_id)},
            {"typ": "oid", "val": str(entra_object_id)},
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
    returned_tenant = next(
        item
        for item in result.structured_content["tenants"]
        if item["tenant_id"] == tenant["tenant_id"]
    )
    assert returned_tenant["effective_role"] == "viewer"
    with postgres_database.connect_owner() as connection:
        audit = connection.execute(
            """
            SELECT tool_call_status, failure_code
              FROM mcp.tool_call_log
             WHERE principal_id = %s
               AND tool_name = 'list_tenants'
             ORDER BY tool_call_time DESC
             LIMIT 1
            """,
            (principal["principal_id"],),
        ).fetchone()
    assert audit == {"tool_call_status": "succeeded", "failure_code": None}


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
