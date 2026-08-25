from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    TenantRole,
)
from gds_etl_workbench.domain.errors import TenantNotFoundError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.tenants import (
    DatabaseTenantService,
    TenantCollection,
    TenantHome,
    TenantLockActions,
    TenantLockState,
    TenantRecord,
    TenantSelection,
    TenantSystemRecord,
)
from gds_workbench_api.main import create_app


class StaticTenantService:
    async def list_tenants(
        self,
        principal: RequestPrincipal,
        *,
        page_size: int,
        cursor: str | None,
    ) -> TenantCollection:
        assert principal == RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        )
        assert page_size == 25
        assert cursor is None
        return TenantCollection(
            items=(
                TenantRecord(
                    tenant_id=7,
                    tenant_code="NWA",
                    tenant_name="Northwind Analytics",
                    tenant_description="Analytics workspace",
                    tenant_visibility="private",
                    effective_role=TenantRole.TENANT_ADMIN,
                ),
            ),
            next_cursor=None,
        )

    async def select_tenant(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> TenantSelection:
        assert principal.entra_object_id == UUID("22222222-2222-2222-2222-222222222222")
        assert tenant_id == 7
        return TenantSelection(tenant_id=tenant_id)

    async def read_tenant_home(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> TenantHome:
        assert principal.actor_kind is ActorKind.HUMAN
        assert tenant_id == 7
        acquired_at = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
        expires_at = datetime(2026, 8, 24, 15, 0, tzinfo=UTC)
        return TenantHome(
            tenant=TenantRecord(
                tenant_id=7,
                tenant_code="NWA",
                tenant_name="Northwind Analytics",
                tenant_description="Analytics workspace",
                tenant_visibility="private",
                effective_role=TenantRole.TENANT_ADMIN,
            ),
            lock=TenantLockState(
                is_locked=True,
                owner_display_name="Maaz",
                owned_by_current_principal=True,
                purpose="Metadata review",
                acquired_at=acquired_at,
                expires_at=expires_at,
            ),
            lock_actions=TenantLockActions(
                can_acquire=False,
                can_renew=True,
                can_release=True,
                can_override=False,
            ),
            systems=(
                TenantSystemRecord(
                    system_id=3,
                    system_code="CRM",
                    system_name="Customer Relationship Management",
                    system_type_name="Salesforce",
                    connection_count=1,
                    registered_object_count=63,
                    active_model_count=2,
                    last_metadata_update_time=expires_at,
                ),
            ),
        )


class MissingTenantService(StaticTenantService):
    async def select_tenant(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> TenantSelection:
        del principal, tenant_id
        raise TenantNotFoundError()


def test_tenant_collection_is_scoped_to_the_server_derived_principal() -> None:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        tenant_service=StaticTenantService(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants?page_size=25")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "tenant_id": 7,
                "tenant_code": "NWA",
                "tenant_name": "Northwind Analytics",
                "tenant_description": "Analytics workspace",
                "tenant_visibility": "private",
                "effective_role": "tenant_admin",
            }
        ],
        "next_cursor": None,
    }


def test_select_tenant_persists_the_server_derived_principal_preference() -> None:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        tenant_service=StaticTenantService(),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/tenants/7/select")

    assert response.status_code == 200
    assert response.json() == {"tenant_id": 7}


def test_select_tenant_returns_a_safe_not_found_error() -> None:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        tenant_service=MissingTenantService(),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/tenants/999/select")

    assert response.status_code == 404
    error = response.json()["error"]
    assert UUID(error.pop("correlation_id"))
    assert error == {
        "code": "tenant_not_found",
        "message": "Tenant was not found.",
        "retryable": False,
    }
    assert response.headers["cache-control"] == "no-store"


def test_tenant_home_keeps_the_lock_as_the_primary_server_owned_state() -> None:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        tenant_service=StaticTenantService(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/home")

    assert response.status_code == 200
    document = response.json()
    assert document["tenant"]["tenant_code"] == "NWA"
    assert document["lock"] == {
        "is_locked": True,
        "owner_display_name": "Maaz",
        "owned_by_current_principal": True,
        "purpose": "Metadata review",
        "acquired_at": "2026-08-24T14:00:00Z",
        "expires_at": "2026-08-24T15:00:00Z",
    }
    assert document["lock_actions"] == {
        "can_acquire": False,
        "can_renew": True,
        "can_release": True,
        "can_override": False,
    }
    assert document["systems"][0]["registered_object_count"] == 63
    assert "gds_instance" not in document


class RecordingTransaction:
    def __init__(self) -> None:
        self.offsets: list[int] = []
        self.preference_calls: list[tuple[Any, ...]] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "application.set_principal_last_tenant" in query:
            self.preference_calls.append(parameters)
            return {"last_tenant_id": 7}
        assert "security.entra_principal_identity" in query
        if len(parameters) == 3:
            assert parameters == (
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                "user",
            )
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
            }
        assert parameters == (
            UUID("11111111-1111-1111-1111-111111111111"),
            UUID("22222222-2222-2222-2222-222222222222"),
            "user",
            7,
        )
        return {
            "principal_id": 41,
            "principal_display_name": "Maaz",
            "is_super_admin": False,
            "effective_role": "tenant_admin",
            "authorized": True,
            "denial_code": None,
            "lock_owner_display_name": None,
            "lock_expires_time": None,
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "security.tenant_principal_access" in query
        assert parameters[:2] == (41, False)
        limit, offset = parameters[2:]
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            {
                "tenant_id": 7,
                "tenant_code": "NWA",
                "tenant_name": "Northwind Analytics",
                "tenant_description": None,
                "tenant_visibility": "private",
                "effective_role": "tenant_admin",
            },
            {
                "tenant_id": 8,
                "tenant_code": "GRDM",
                "tenant_name": "Global Reference Data",
                "tenant_description": None,
                "tenant_visibility": "global",
                "effective_role": "viewer",
            },
        ]
        return rows[offset : offset + limit]


class RecordingDatabase:
    def __init__(self) -> None:
        self.transaction = RecordingTransaction()
        self.isolations: list[ReadIsolation] = []

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[RecordingTransaction]:
        self.isolations.append(isolation)
        yield self.transaction

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[RecordingTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_database_tenant_service_reuses_authorization_and_signed_paging() -> None:
    database = RecordingDatabase()
    service = DatabaseTenantService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    first = await service.list_tenants(principal, page_size=1, cursor=None)
    second = await service.list_tenants(
        principal,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert [item.tenant_code for item in first.items] == ["NWA"]
    assert [item.tenant_code for item in second.items] == ["GRDM"]
    assert second.next_cursor is None
    assert database.transaction.offsets == [0, 1]
    assert database.isolations == [
        ReadIsolation.REPEATABLE_READ,
        ReadIsolation.REPEATABLE_READ,
    ]


@pytest.mark.asyncio
async def test_database_tenant_selection_reauthorizes_and_calls_the_governed_function() -> (
    None
):
    database = RecordingDatabase()
    service = DatabaseTenantService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    selected = await service.select_tenant(principal, tenant_id=7)

    assert selected == TenantSelection(tenant_id=7)
    assert database.transaction.preference_calls == [
        (
            UUID("11111111-1111-1111-1111-111111111111"),
            UUID("22222222-2222-2222-2222-222222222222"),
            "user",
            7,
        )
    ]


class TenantHomeTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "WITH actor AS" in query:
            assert parameters[-1] == 7
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
                "effective_role": "tenant_admin",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": None,
            }
        if "tenant.tenant_description" in query:
            assert parameters == (7,)
            return {
                "tenant_id": 7,
                "tenant_code": "NWA",
                "tenant_name": "Northwind Analytics",
                "tenant_description": None,
                "tenant_visibility": "private",
            }
        assert "security.tenant_lock" in query
        assert parameters == (41, 7)
        return {
            "owner_display_name": "Elena Morris",
            "owned_by_current_principal": False,
            "purpose": "Logical review",
            "acquired_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            "expires_at": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "registered_object_count" in query
        assert parameters == (7, 7)
        return [
            {
                "system_id": 3,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
                "system_type_name": "Salesforce",
                "connection_count": 1,
                "registered_object_count": 63,
                "active_model_count": 2,
                "last_metadata_update_time": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            }
        ]


class TenantHomeDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[TenantHomeTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield TenantHomeTransaction()

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[TenantHomeTransaction]:
        raise AssertionError("home is read only")
        yield TenantHomeTransaction()


@pytest.mark.asyncio
async def test_database_tenant_home_derives_lock_actions_from_role_and_ownership() -> (
    None
):
    service = DatabaseTenantService(
        database=TenantHomeDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    home = await service.read_tenant_home(
        RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        tenant_id=7,
    )

    assert home.lock.owner_display_name == "Elena Morris"
    assert home.lock_actions == TenantLockActions(
        can_acquire=False,
        can_renew=False,
        can_release=False,
        can_override=True,
    )
    assert home.systems[0].active_model_count == 2
