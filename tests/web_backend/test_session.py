import base64
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, LiteralString
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.main import create_app
from gds_workbench_api.features.session import DatabaseSessionService, SessionRecord


class StaticSessionService:
    async def read_session(self, principal: RequestPrincipal) -> SessionRecord:
        assert principal == RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        )
        return SessionRecord(
            display_name="Maaz",
            actor_kind=ActorKind.HUMAN,
            is_super_admin=False,
            last_tenant_id=7,
        )


def _easy_auth_header() -> str:
    value = {
        "auth_typ": "aad",
        "claims": [
            {"typ": "tid", "val": "11111111-1111-1111-1111-111111111111"},
            {"typ": "oid", "val": "22222222-2222-2222-2222-222222222222"},
            {"typ": "idtyp", "val": "user"},
            {"typ": "scp", "val": "workbench.access"},
        ],
    }
    return base64.b64encode(json.dumps(value).encode()).decode()


def test_session_uses_the_server_derived_easy_auth_identity() -> None:
    app = create_app(
        identity_provider=IdentityProvider(AuthMode.AZURE_EASY_AUTH),
        session_service=StaticSessionService(),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/session",
            headers={"x-ms-client-principal": _easy_auth_header()},
        )

    assert response.status_code == 200
    assert response.json() == {
        "display_name": "Maaz",
        "actor_kind": "human",
        "is_super_admin": False,
        "last_tenant_id": 7,
    }


def test_session_rejects_a_missing_easy_auth_identity_with_a_safe_error() -> None:
    app = create_app(
        identity_provider=IdentityProvider(AuthMode.AZURE_EASY_AUTH),
        session_service=StaticSessionService(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/session")

    assert response.status_code == 401
    error = response.json()["error"]
    assert UUID(error.pop("correlation_id"))
    assert error == {
        "code": "authentication_required",
        "message": "Authentication is required.",
        "retryable": False,
    }
    assert response.headers["cache-control"] == "no-store"


class SessionTransaction:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.queries.append(query)
        if "security.entra_principal_identity" in query:
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
            }
        assert "application.principal_preference" in query
        assert parameters == (41, False)
        return {"last_tenant_id": 7}

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class SessionDatabase:
    def __init__(self) -> None:
        self.transaction = SessionTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[SessionTransaction]:
        assert isolation is ReadIsolation.READ_COMMITTED
        yield self.transaction


@pytest.mark.asyncio
async def test_database_session_returns_only_a_currently_visible_last_tenant() -> None:
    database = SessionDatabase()
    service = DatabaseSessionService(
        database=database,
        authorizer=AuthorizationService(),
    )

    session = await service.read_session(
        RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        )
    )

    assert session == SessionRecord(
        display_name="Maaz",
        actor_kind=ActorKind.HUMAN,
        is_super_admin=False,
        last_tenant_id=7,
    )
    assert len(database.transaction.queries) == 2
