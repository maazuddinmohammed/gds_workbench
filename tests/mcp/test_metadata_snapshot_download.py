from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

from mcp.server.mcpserver import MCPServer
from starlette.testclient import TestClient

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.errors import AuthorizationDeniedError
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
)
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    register_metadata_snapshot_download_route,
)

SNAPSHOT_ID = UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233")
NOW = datetime(2026, 8, 11, 16, 0, tzinfo=UTC)


class FakeTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        raise AssertionError("development authorization must not query")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError("download authorization must not select snapshot rows")


class FakeDatabase:
    def __init__(self) -> None:
        self.transaction_count = 0

    async def open(self) -> None:
        raise AssertionError("download route must not open the database")

    async def close(self) -> None:
        raise AssertionError("download route must not close the database")

    async def readiness(self) -> ReadinessRecord:
        raise AssertionError("download route must not check database readiness")

    async def expire_tenant_locks(self) -> int:
        raise AssertionError("download route must not expire tenant locks")

    async def append_tool_call_log(self, record: ToolCallLogRecord) -> None:
        del record
        raise AssertionError("download route must not append a tool-call log")

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncIterator[ReadTransaction]:
        assert isolation is ReadIsolation.READ_COMMITTED
        self.transaction_count += 1
        yield FakeTransaction()


class FakeStore:
    def __init__(self, read_url: str | None) -> None:
        self.read_url = read_url
        self.calls: list[tuple[int, UUID, datetime, int]] = []

    async def close(self) -> None:
        return None

    async def upload_archive(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("download must not upload")

    async def create_read_url(
        self,
        *,
        tenant_id: int,
        snapshot_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> str | None:
        self.calls.append((tenant_id, snapshot_id, now, ttl_seconds))
        return self.read_url


class DenyingAuthorizer(AuthorizationService):
    async def authorize_tenant(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AuthorizationDeniedError()


def test_download_reauthorizes_and_redirects_without_caching() -> None:
    database = FakeDatabase()
    store = FakeStore("https://blob.example/snapshot.zip?sp=r&sig=secret")
    application = _application(database, store, AuthorizationService())

    with TestClient(application) as client:
        response = client.get(
            f"/metadata-snapshots/123/{SNAPSHOT_ID}/download",
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == store.read_url
    assert response.headers["cache-control"] == "no-store"
    assert database.transaction_count == 1
    assert store.calls == [(123, SNAPSHOT_ID, NOW, 900)]


def test_download_hides_unauthorized_missing_and_malformed_identifiers() -> None:
    database = FakeDatabase()
    store = FakeStore(None)

    missing_application = _application(database, store, AuthorizationService())
    with TestClient(missing_application) as client:
        missing = client.get(
            f"/metadata-snapshots/123/{SNAPSHOT_ID}/download",
            follow_redirects=False,
        )
        malformed = client.get(
            "/metadata-snapshots/001/not-a-uuid/download",
            follow_redirects=False,
        )

    denied_application = _application(database, store, DenyingAuthorizer())
    with TestClient(denied_application) as client:
        denied = client.get(
            f"/metadata-snapshots/123/{SNAPSHOT_ID}/download",
            follow_redirects=False,
        )

    assert missing.status_code == 404
    assert malformed.status_code == 404
    assert denied.status_code == 404
    assert missing.json() == malformed.json() == denied.json()
    assert all(
        response.headers["cache-control"] == "no-store" for response in (missing, malformed, denied)
    )
    assert len(store.calls) == 1


def _application(
    database: FakeDatabase,
    store: FakeStore,
    authorizer: AuthorizationService,
) -> Any:
    server = MCPServer[None](name="snapshot-download-test")
    register_metadata_snapshot_download_route(
        server,
        database=database,
        identity_provider=IdentityProvider(AuthMode.DEV),
        authorizer=authorizer,
        store=store,
        download_ttl_seconds=900,
        clock=lambda: NOW,
    )
    return server.streamable_http_app(json_response=True, stateless_http=True)
