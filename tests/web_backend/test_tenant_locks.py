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
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.tenant_locks import (
    DatabaseTenantLockService,
    LockHistoryEvent,
    LockHistoryPage,
    TenantLockMutation,
    TenantLockRecord,
)
from gds_workbench_api.main import create_app


class StaticTenantLockService:
    def __init__(self) -> None:
        self.actions: list[tuple[object, ...]] = []

    async def acquire(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        duration_minutes: int,
        purpose: str | None,
    ) -> TenantLockMutation:
        assert principal.actor_kind is ActorKind.HUMAN
        self.actions.append(("acquire", tenant_id, duration_minutes, purpose))
        return TenantLockMutation(
            tenant_id=tenant_id,
            action="acquired",
            lock=TenantLockRecord(
                owner_display_name="Maaz",
                owned_by_current_principal=True,
                purpose=purpose,
                acquired_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                expires_at=datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            ),
        )

    async def renew(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        duration_minutes: int,
    ) -> TenantLockMutation:
        assert principal.actor_kind is ActorKind.HUMAN
        self.actions.append(("renew", tenant_id, duration_minutes))
        return TenantLockMutation(
            tenant_id=tenant_id,
            action="renewed",
            lock=TenantLockRecord(
                owner_display_name="Maaz",
                owned_by_current_principal=True,
                acquired_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                expires_at=datetime(2026, 8, 24, 16, 0, tzinfo=UTC),
            ),
        )

    async def release(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> TenantLockMutation:
        assert principal.actor_kind is ActorKind.HUMAN
        self.actions.append(("release", tenant_id))
        return TenantLockMutation(tenant_id=tenant_id, action="released")

    async def override(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        reason: str,
    ) -> TenantLockMutation:
        assert principal.actor_kind is ActorKind.HUMAN
        self.actions.append(("override", tenant_id, reason))
        return TenantLockMutation(
            tenant_id=tenant_id,
            action="overridden",
            previous_lock=TenantLockRecord(
                owner_display_name="Elena Morris",
                owned_by_current_principal=False,
                purpose="Metadata review",
                acquired_at=datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                expires_at=datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            ),
        )

    async def history(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        page_size: int,
        cursor: str | None,
    ) -> LockHistoryPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, page_size, cursor) == (7, 25, None)
        return LockHistoryPage(
            tenant_id=tenant_id,
            items=(
                LockHistoryEvent(
                    event_id=901,
                    event_type="acquired",
                    owner_display_name="Maaz",
                    actor_display_name="Maaz",
                    reason=None,
                    acquired_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                    expires_at=datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
                    created_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )


def _app(service: StaticTenantLockService):
    return create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        tenant_lock_service=service,
    )


def test_lock_actions_are_explicit_and_override_does_not_acquire() -> None:
    service = StaticTenantLockService()
    with TestClient(_app(service)) as client:
        acquire = client.post(
            "/api/v1/tenants/7/lock/acquire",
            json={"duration_minutes": 60, "purpose": "Metadata review"},
        )
        override = client.post(
            "/api/v1/tenants/7/lock/override",
            json={"reason": "Owner is unavailable"},
        )

    assert acquire.status_code == 200
    assert acquire.json()["action"] == "acquired"
    assert override.status_code == 200
    assert override.json()["action"] == "overridden"
    assert override.json()["lock"] is None
    assert service.actions == [
        ("acquire", 7, 60, "Metadata review"),
        ("override", 7, "Owner is unavailable"),
    ]


def test_lock_history_is_bounded_and_tenant_scoped() -> None:
    with TestClient(_app(StaticTenantLockService())) as client:
        response = client.get("/api/v1/tenants/7/lock/history?page_size=25")

    assert response.status_code == 200
    assert response.json()["items"][0]["event_type"] == "acquired"


class LockTransaction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
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
        if "security.acquire_tenant_lock" in query:
            action = "acquire"
            row = {
                "acquired": True,
                "denial_code": None,
                "owner_display_name": "Maaz",
                "purpose": "Metadata review",
                "acquired_time": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                "expires_time": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            }
        elif "security.renew_tenant_lock" in query:
            action = "renew"
            row = {
                "renewed": True,
                "denial_code": None,
                "owner_display_name": "Maaz",
                "purpose": "Metadata review",
                "acquired_time": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                "expires_time": datetime(2026, 8, 24, 16, 0, tzinfo=UTC),
            }
        elif "security.release_tenant_lock" in query:
            action = "release"
            row = {"released": True, "denial_code": None}
        else:
            assert "security.override_tenant_lock" in query
            action = "override"
            row = {
                "overridden": True,
                "denial_code": None,
                "previous_owner_display_name": "Elena Morris",
                "previous_owned_by_current_principal": False,
                "previous_purpose": "Metadata review",
                "previous_acquired_time": datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
                "previous_expires_time": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            }
        self.calls.append((action, parameters))
        return row

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "security.tenant_lock_event" in query
        self.calls.append(("history", parameters))
        return [
            {
                "event_id": 901,
                "event_type": "acquired",
                "owner_display_name": "Maaz",
                "actor_display_name": "Maaz",
                "reason": None,
                "acquired_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                "expires_at": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
                "created_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
        ]


class LockDatabase:
    def __init__(self) -> None:
        self.transaction = LockTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[LockTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[LockTransaction]:
        yield self.transaction


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


@pytest.mark.asyncio
async def test_database_lock_operations_call_only_governed_functions() -> None:
    database = LockDatabase()
    service = DatabaseTenantLockService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    await service.acquire(
        _principal(),
        tenant_id=7,
        duration_minutes=60,
        purpose="Metadata review",
    )
    await service.renew(_principal(), tenant_id=7, duration_minutes=120)
    await service.release(_principal(), tenant_id=7)
    overridden = await service.override(
        _principal(), tenant_id=7, reason="Owner is unavailable"
    )

    identity = (
        UUID("11111111-1111-1111-1111-111111111111"),
        UUID("22222222-2222-2222-2222-222222222222"),
        "user",
        7,
    )
    assert database.transaction.calls == [
        ("acquire", (*identity, 60, "Metadata review")),
        ("renew", (*identity, 120)),
        ("release", identity),
        ("override", (*identity, "Owner is unavailable")),
    ]
    assert overridden.lock is None
    assert overridden.previous_lock is not None


@pytest.mark.asyncio
async def test_database_lock_history_reauthorizes_and_pages_safely() -> None:
    database = LockDatabase()
    service = DatabaseTenantLockService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    page = await service.history(
        _principal(),
        tenant_id=7,
        page_size=25,
        cursor=None,
    )

    assert page.items[0].owner_display_name == "Maaz"
    assert page.next_cursor is None
    assert database.transaction.calls == [("history", (7, 26, 0))]
