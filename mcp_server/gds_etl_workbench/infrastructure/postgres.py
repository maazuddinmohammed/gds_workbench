"""Least-privilege PostgreSQL persistence adapter."""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg import Error as PsycopgError
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from gds_etl_workbench.application.ports import ReadinessRecord, TenantRecord
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal, TenantRole
from gds_etl_workbench.domain.errors import AuthorizationDeniedError, DependencyUnavailableError

_READINESS_SQL = """
WITH runtime_role AS (
    SELECT oid, rolsuper, rolcreatedb, rolcreaterole
      FROM pg_catalog.pg_roles
     WHERE rolname = SESSION_USER
)
SELECT current_setting('server_version_num')::INTEGER / 10000 AS postgres_major,
       to_regclass('core.tenant') IS NOT NULL
       AND to_regclass('security.principal') IS NOT NULL
       AND to_regclass('security.entra_principal_identity') IS NOT NULL
       AND to_regclass('security.tenant_principal_access') IS NOT NULL
       AND to_regprocedure(
           'security.resolve_principal_access(uuid,uuid,bigint)'
       ) IS NOT NULL AS schema_shape_ok,
       CURRENT_USER = 'gds_app_write'
       AND NOT runtime_role.rolsuper
       AND NOT runtime_role.rolcreatedb
       AND NOT runtime_role.rolcreaterole
       AND (
           SELECT count(*) = 1
             FROM pg_catalog.pg_auth_members AS membership
            WHERE membership.member = runtime_role.oid
       )
       AND EXISTS (
           SELECT 1
             FROM pg_catalog.pg_auth_members AS membership
             JOIN pg_catalog.pg_roles AS granted_role
               ON granted_role.oid = membership.roleid
            WHERE membership.member = runtime_role.oid
              AND granted_role.rolname = 'gds_app_write'
       ) AS runtime_role_ok
  FROM runtime_role
"""

_RESOLVE_PRINCIPAL_SQL = """
SELECT principal.principal_id, principal.is_super_admin
  FROM security.entra_principal_identity AS identity
  JOIN security.principal AS principal
    ON principal.principal_id = identity.principal_id
   AND principal.principal_type = identity.principal_type
 WHERE identity.entra_tenant_id = %s
   AND identity.entra_object_id = %s
   AND identity.principal_type = 'user'
   AND identity.is_active
   AND principal.is_active
 FOR SHARE OF identity, principal
"""

_AUTHORIZED_TENANTS_SQL = """
SELECT tenant.tenant_id,
       tenant.tenant_code,
       tenant.tenant_name,
       left(tenant.tenant_description, 2000) AS tenant_description,
       tenant.tenant_visibility,
       CASE
           WHEN %s THEN 'super_admin'
           WHEN membership.tenant_role IS NOT NULL THEN membership.tenant_role
           ELSE 'viewer'
       END AS effective_role
  FROM core.tenant AS tenant
  LEFT JOIN security.tenant_principal_access AS membership
    ON membership.tenant_id = tenant.tenant_id
   AND membership.principal_id = %s
   AND membership.is_active
   AND (
       membership.access_expires_time IS NULL
       OR membership.access_expires_time > CURRENT_TIMESTAMP
   )
 WHERE tenant.is_active
   AND (%s OR tenant.tenant_visibility = 'global' OR membership.tenant_id IS NOT NULL)
 ORDER BY lower(tenant.tenant_name), tenant.tenant_id
 LIMIT %s OFFSET %s
"""

_DEV_TENANTS_SQL = """
SELECT tenant.tenant_id,
       tenant.tenant_code,
       tenant.tenant_name,
       left(tenant.tenant_description, 2000) AS tenant_description,
       tenant.tenant_visibility,
       'development' AS effective_role
  FROM core.tenant AS tenant
 WHERE tenant.is_active
 ORDER BY lower(tenant.tenant_name), tenant.tenant_id
 LIMIT %s OFFSET %s
"""


async def _activate_runtime_role(connection: AsyncConnection[Any]) -> None:
    """Activate the only NOINHERIT group role allowed for the production login."""
    await connection.execute("SET ROLE gds_app_write")


class PostgresRepository:
    def __init__(
        self,
        *,
        dsn: str,
        pool_min: int,
        pool_max: int,
        pool_timeout_seconds: int,
        require_runtime_role: bool,
    ) -> None:
        self._require_runtime_role = require_runtime_role
        self._pool = AsyncConnectionPool(
            conninfo=dsn,
            min_size=pool_min,
            max_size=pool_max,
            timeout=pool_timeout_seconds,
            kwargs={"autocommit": True, "row_factory": dict_row},
            configure=_activate_runtime_role if require_runtime_role else None,
            open=False,
            name="gds-mcp",
        )

    async def open(self) -> None:
        await self._pool.open(wait=False)

    async def close(self) -> None:
        await self._pool.close()

    async def readiness(self) -> ReadinessRecord:
        try:
            async with self._pool.connection() as connection:
                result = await connection.execute(_READINESS_SQL)
                row = await result.fetchone()
            if row is None:
                return ReadinessRecord(ready=False, code="database_posture_invalid")
            if row["postgres_major"] != 16:
                return ReadinessRecord(ready=False, code="database_version_invalid")
            if not row["schema_shape_ok"]:
                return ReadinessRecord(ready=False, code="database_schema_unavailable")
            if self._require_runtime_role and not row["runtime_role_ok"]:
                return ReadinessRecord(ready=False, code="database_role_invalid")
            return ReadinessRecord(ready=True, code="ready")
        except PsycopgError:
            return ReadinessRecord(ready=False, code="database_unavailable")

    async def list_tenants(
        self, principal: RequestPrincipal, *, limit: int, offset: int
    ) -> list[TenantRecord]:
        try:
            async with self._pool.connection() as connection, connection.transaction():
                await connection.execute("SET TRANSACTION READ ONLY")
                if principal.actor_kind is ActorKind.DEVELOPMENT:
                    result = await connection.execute(_DEV_TENANTS_SQL, (limit, offset))
                else:
                    if principal.entra_tenant_id is None or principal.entra_object_id is None:
                        raise AuthorizationDeniedError()
                    resolved = await connection.execute(
                        _RESOLVE_PRINCIPAL_SQL,
                        (principal.entra_tenant_id, principal.entra_object_id),
                    )
                    actor: dict[str, Any] | None = await resolved.fetchone()
                    if actor is None:
                        raise AuthorizationDeniedError()
                    result = await connection.execute(
                        _AUTHORIZED_TENANTS_SQL,
                        (
                            actor["is_super_admin"],
                            actor["principal_id"],
                            actor["is_super_admin"],
                            limit,
                            offset,
                        ),
                    )
                rows: list[dict[str, Any]] = await result.fetchall()
        except AuthorizationDeniedError:
            raise
        except PsycopgError as exc:
            raise DependencyUnavailableError() from exc

        return [
            TenantRecord(
                tenant_id=row["tenant_id"],
                tenant_code=row["tenant_code"],
                tenant_name=row["tenant_name"],
                tenant_description=row["tenant_description"],
                tenant_visibility=row["tenant_visibility"],
                effective_role=TenantRole(row["effective_role"]),
            )
            for row in rows
        ]
