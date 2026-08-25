"""Server-derived Principal Session authorization and persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
)

from gds_workbench_api.features.session.contracts import SessionRecord

_VISIBLE_LAST_TENANT_SQL = """
SELECT preference.last_tenant_id
  FROM application.principal_preference AS preference
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = preference.last_tenant_id
   AND tenant.is_active
  LEFT JOIN security.tenant_principal_access AS access
    ON access.tenant_id = tenant.tenant_id
   AND access.principal_id = preference.principal_id
   AND access.is_active
   AND (
       access.access_expires_time IS NULL
       OR access.access_expires_time > CURRENT_TIMESTAMP
   )
 WHERE preference.principal_id = %s
   AND (
       %s::BOOLEAN
       OR tenant.tenant_visibility = 'global'
       OR access.tenant_id IS NOT NULL
   )
"""


class SessionService(Protocol):
    async def read_session(self, principal: RequestPrincipal) -> SessionRecord: ...


class SessionReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseSessionService:
    def __init__(
        self,
        *,
        database: SessionReadDatabase,
        authorizer: AuthorizationService,
    ) -> None:
        self._database = database
        self._authorizer = authorizer

    async def read_session(self, principal: RequestPrincipal) -> SessionRecord:
        async with self._database.read_transaction() as transaction:
            actor = await self._authorizer.resolve_principal(transaction, principal)
            preference = None
            if actor.principal_id is not None:
                preference = await transaction.fetch_one(
                    _VISIBLE_LAST_TENANT_SQL,
                    (actor.principal_id, actor.is_super_admin),
                )

        return SessionRecord(
            display_name=actor.display_name,
            actor_kind=actor.actor_kind,
            is_super_admin=actor.is_super_admin,
            last_tenant_id=(None if preference is None else preference["last_tenant_id"]),
        )
