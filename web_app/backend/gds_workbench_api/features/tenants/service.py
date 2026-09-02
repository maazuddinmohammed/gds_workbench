"""Tenant entry authorization and persistence."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    TenantRole,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    TenantNotFoundError,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_etl_workbench.tools.tenants.list_tenants import query_visible_tenants

from gds_workbench_api.features.tenants.contracts import (
    TenantCollection,
    TenantHome,
    TenantLockActions,
    TenantLockState,
    TenantRecord,
    TenantSelection,
    TenantSystemRecord,
)

_TENANT_COLLECTION = "web_tenants"
_SET_LAST_TENANT_SQL = """
SELECT last_tenant_id
  FROM application.set_principal_last_tenant(%s, %s, %s, %s)
"""
_TENANT_HOME_SQL = """
SELECT tenant.tenant_id,
       tenant.tenant_code,
       tenant.tenant_name,
       left(tenant.tenant_description, 2000) AS tenant_description,
       tenant.tenant_visibility
  FROM core.tenant AS tenant
 WHERE tenant.tenant_id = %s
   AND tenant.is_active
"""
_ACTIVE_TENANT_LOCK_SQL = """
SELECT principal.principal_display_name AS owner_display_name,
       tenant_lock.locked_by_principal_id = %s AS owned_by_current_principal,
       tenant_lock.tenant_lock_purpose AS purpose,
       tenant_lock.tenant_lock_acquired_time AS acquired_at,
       tenant_lock.tenant_lock_expires_time AS expires_at
  FROM security.tenant_lock AS tenant_lock
  JOIN security.principal AS principal
    ON principal.principal_id = tenant_lock.locked_by_principal_id
   AND principal.is_active
 WHERE tenant_lock.tenant_id = %s
   AND tenant_lock.tenant_lock_expires_time > CURRENT_TIMESTAMP
"""
_TENANT_SYSTEMS_SQL = """
SELECT system.system_id,
       system.system_code,
       system.system_name,
       system_type.system_type_name,
       count(DISTINCT connection.connection_id)::INTEGER AS connection_count,
       count(DISTINCT object.object_id)::INTEGER AS registered_object_count,
       count(DISTINCT model.model_id)::INTEGER AS active_model_count,
       max(object.updated_time) AS last_metadata_update_time
  FROM core.connection AS connection
  JOIN core.system AS system
    ON system.system_id = connection.system_id
   AND system.is_active
  JOIN reference.system_type AS system_type
    ON system_type.system_type_id = system.system_type_id
   AND system_type.is_active
  LEFT JOIN core.object AS object
    ON object.connection_id = connection.connection_id
   AND object.is_active
  LEFT JOIN model.model_input_scope AS scope
    ON scope.object_id = object.object_id
   AND scope.is_active
  LEFT JOIN model.model AS model
    ON model.model_id = scope.model_id
   AND model.tenant_id = %s
   AND model.is_active
 WHERE connection.tenant_id = %s
   AND connection.is_active
 GROUP BY system.system_id,
          system.system_code,
          system.system_name,
          system_type.system_type_name
 ORDER BY lower(system.system_name), system.system_id
"""


class TenantService(Protocol):
    async def list_tenants(
        self,
        principal: RequestPrincipal,
        *,
        page_size: int,
        cursor: str | None,
    ) -> TenantCollection: ...

    async def select_tenant(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> TenantSelection: ...

    async def read_tenant_home(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> TenantHome: ...


class TenantDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...

    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseTenantService:
    """List authorized Workbench Tenants without GDS Connection owners."""

    def __init__(
        self,
        *,
        database: TenantDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_tenants(
        self,
        principal: RequestPrincipal,
        *,
        page_size: int,
        cursor: str | None,
    ) -> TenantCollection:
        offset = self._cursors.decode(cursor, collection=_TENANT_COLLECTION)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            actor = await self._authorizer.resolve_principal(transaction, principal)
            rows = await query_visible_tenants(
                transaction,
                actor,
                limit=page_size + 1,
                offset=offset,
                include_global_data_store_owner_tenants=False,
            )

        items = tuple(TenantRecord.model_validate(row) for row in rows[:page_size])
        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=_TENANT_COLLECTION,
                offset=offset + page_size,
            )
        return TenantCollection(items=items, next_cursor=next_cursor)

    async def select_tenant(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> TenantSelection:
        if principal.entra_tenant_id is None or principal.entra_object_id is None:
            raise AuthorizationDeniedError()
        expected_type = (
            "service_principal" if principal.actor_kind is ActorKind.WORKLOAD else "user"
        )
        async with self._database.write_transaction() as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            row = await transaction.fetch_one(
                _SET_LAST_TENANT_SQL,
                (
                    principal.entra_tenant_id,
                    principal.entra_object_id,
                    expected_type,
                    tenant_id,
                ),
            )
        if row is None or row.get("last_tenant_id") != tenant_id:
            raise DependencyUnavailableError()
        return TenantSelection(tenant_id=tenant_id)

    async def read_tenant_home(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> TenantHome:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            tenant_row = await transaction.fetch_one(_TENANT_HOME_SQL, (tenant_id,))
            if tenant_row is None:
                raise TenantNotFoundError()
            principal_id = authorization.principal.principal_id
            lock_row = (
                None
                if principal_id is None
                else await transaction.fetch_one(
                    _ACTIVE_TENANT_LOCK_SQL,
                    (principal_id, tenant_id),
                )
            )
            system_rows = await transaction.fetch_all(
                _TENANT_SYSTEMS_SQL,
                (tenant_id, tenant_id),
            )

        lock = (
            TenantLockState(is_locked=False)
            if lock_row is None
            else TenantLockState(is_locked=True, **lock_row)
        )
        can_manage_lock = (
            principal.actor_kind is ActorKind.HUMAN
            and principal.entra_tenant_id is not None
            and principal.entra_object_id is not None
            and authorization.effective_role
            in {
                TenantRole.DEVELOPER,
                TenantRole.ARCHITECT,
                TenantRole.TENANT_ADMIN,
                TenantRole.SUPER_ADMIN,
            }
        )
        owns_lock = lock.owned_by_current_principal is True
        return TenantHome(
            tenant=TenantRecord(
                **tenant_row,
                effective_role=authorization.effective_role,
            ),
            lock=lock,
            lock_actions=TenantLockActions(
                can_acquire=can_manage_lock and not lock.is_locked,
                can_renew=can_manage_lock and owns_lock,
                can_release=can_manage_lock and owns_lock,
                can_override=can_manage_lock and lock.is_locked and not owns_lock,
            ),
            systems=tuple(TenantSystemRecord.model_validate(row) for row in system_rows),
        )
