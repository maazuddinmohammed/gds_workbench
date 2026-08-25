"""Explicit governed Tenant Lock authorization and persistence."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    InvalidRequestError,
    TenantLockedError,
    TenantLockRequiredError,
    TenantNotFoundError,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)

from gds_workbench_api.features.tenant_locks.contracts import (
    LockHistoryEvent,
    LockHistoryPage,
    TenantLockMutation,
    TenantLockRecord,
)

_ACQUIRE_SQL = """
SELECT acquired,
       denial_code,
       owner_display_name,
       purpose,
       acquired_time,
       expires_time
  FROM security.acquire_tenant_lock(%s, %s, %s, %s, %s, %s)
"""

_RENEW_SQL = """
SELECT renewed,
       denial_code,
       owner_display_name,
       purpose,
       acquired_time,
       expires_time
  FROM security.renew_tenant_lock(%s, %s, %s, %s, %s)
"""

_RELEASE_SQL = """
SELECT released,
       denial_code
  FROM security.release_tenant_lock(%s, %s, %s, %s)
"""

_OVERRIDE_SQL = """
SELECT overridden,
       denial_code,
       previous_owner_display_name,
       previous_owned_by_current_principal,
       previous_purpose,
       previous_acquired_time,
       previous_expires_time
  FROM security.override_tenant_lock(%s, %s, %s, %s, %s)
"""

_HISTORY_SQL = """
SELECT event.tenant_lock_event_id AS event_id,
       event.tenant_lock_event_type AS event_type,
       owner.principal_display_name AS owner_display_name,
       actor.principal_display_name AS actor_display_name,
       left(event.tenant_lock_event_reason, 2000) AS reason,
       event.tenant_lock_acquired_time AS acquired_at,
       event.tenant_lock_expires_time AS expires_at,
       event.created_time AS created_at
  FROM security.tenant_lock_event AS event
  JOIN security.principal AS owner
    ON owner.principal_id = event.lock_owner_principal_id
  LEFT JOIN security.principal AS actor
    ON actor.principal_id = event.lock_acted_by_principal_id
 WHERE event.tenant_id = %s
 ORDER BY event.created_time DESC,
          event.tenant_lock_event_id DESC
 LIMIT %s OFFSET %s
"""


class TenantLockService(Protocol):
    async def acquire(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        duration_minutes: int,
        purpose: str | None,
    ) -> TenantLockMutation: ...

    async def renew(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        duration_minutes: int,
    ) -> TenantLockMutation: ...

    async def release(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> TenantLockMutation: ...

    async def override(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        reason: str,
    ) -> TenantLockMutation: ...

    async def history(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        page_size: int,
        cursor: str | None,
    ) -> LockHistoryPage: ...


class TenantLockDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...

    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseTenantLockService:
    def __init__(
        self,
        *,
        database: TenantLockDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def acquire(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        duration_minutes: int,
        purpose: str | None,
    ) -> TenantLockMutation:
        identity = _identity_arguments(principal)
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _ACQUIRE_SQL,
                (*identity, tenant_id, duration_minutes, purpose),
            )
        _raise_lock_denial(row, success_field="acquired")
        assert row is not None
        return TenantLockMutation(
            tenant_id=tenant_id,
            action="acquired",
            lock=_lock_record(row, owned_by_current_principal=True),
        )

    async def renew(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        duration_minutes: int,
    ) -> TenantLockMutation:
        identity = _identity_arguments(principal)
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _RENEW_SQL,
                (*identity, tenant_id, duration_minutes),
            )
        _raise_lock_denial(row, success_field="renewed")
        assert row is not None
        return TenantLockMutation(
            tenant_id=tenant_id,
            action="renewed",
            lock=_lock_record(row, owned_by_current_principal=True),
        )

    async def release(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> TenantLockMutation:
        identity = _identity_arguments(principal)
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _RELEASE_SQL,
                (*identity, tenant_id),
            )
        _raise_lock_denial(row, success_field="released")
        return TenantLockMutation(tenant_id=tenant_id, action="released")

    async def override(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        reason: str,
    ) -> TenantLockMutation:
        identity = _identity_arguments(principal)
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _OVERRIDE_SQL,
                (*identity, tenant_id, reason),
            )
        _raise_override_denial(row)
        assert row is not None
        return TenantLockMutation(
            tenant_id=tenant_id,
            action="overridden",
            previous_lock=TenantLockRecord(
                owner_display_name=row["previous_owner_display_name"],
                owned_by_current_principal=False,
                purpose=row["previous_purpose"],
                acquired_at=row["previous_acquired_time"],
                expires_at=row["previous_expires_time"],
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
        collection = f"web_tenant_lock_history:{tenant_id}:{page_size}"
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            rows = await transaction.fetch_all(
                _HISTORY_SQL,
                (tenant_id, page_size + 1, offset),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return LockHistoryPage(
            tenant_id=tenant_id,
            items=tuple(LockHistoryEvent.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )


def _identity_arguments(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if (
        principal.actor_kind is not ActorKind.HUMAN
        or principal.entra_tenant_id is None
        or principal.entra_object_id is None
    ):
        raise AuthorizationDeniedError()
    return principal.entra_tenant_id, principal.entra_object_id, "user"


def _raise_lock_denial(
    row: Mapping[str, Any] | None,
    *,
    success_field: str,
) -> None:
    if row is None:
        raise AuthorizationDeniedError()
    if row[success_field] is True:
        return
    denial_code = row["denial_code"]
    if denial_code == "tenant_not_found":
        raise TenantNotFoundError()
    if denial_code == "tenant_locked":
        owner = row.get("owner_display_name")
        safe_owner = " ".join(owner.split())[:200] if isinstance(owner, str) else ""
        raise TenantLockedError(safe_owner or "another Principal")
    if denial_code == "tenant_lock_required":
        raise TenantLockRequiredError()
    raise AuthorizationDeniedError()


def _raise_override_denial(row: Mapping[str, Any] | None) -> None:
    if row is None:
        raise AuthorizationDeniedError()
    if row["overridden"] is True:
        return
    denial_code = row["denial_code"]
    if denial_code == "tenant_not_found":
        raise TenantNotFoundError()
    if denial_code == "tenant_lock_required":
        raise InvalidRequestError("Tenant is not currently locked.")
    if denial_code == "tenant_locked" and row.get("previous_owned_by_current_principal") is True:
        raise InvalidRequestError(
            "The current Principal owns this Tenant Lock; release it instead."
        )
    raise AuthorizationDeniedError()


def _lock_record(
    row: Mapping[str, Any],
    *,
    owned_by_current_principal: bool,
) -> TenantLockRecord:
    return TenantLockRecord(
        owner_display_name=row["owner_display_name"],
        owned_by_current_principal=owned_by_current_principal,
        purpose=row["purpose"],
        acquired_at=row["acquired_time"],
        expires_at=row["expires_time"],
    )
