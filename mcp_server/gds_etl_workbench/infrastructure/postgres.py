"""Least-privilege PostgreSQL persistence adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any, LiteralString, Protocol

from psycopg import AsyncConnection
from psycopg import Error as PsycopgError
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from gds_etl_workbench.domain.errors import DependencyUnavailableError

type QueryParameters = tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class ReadinessRecord:
    ready: bool
    code: str


class ReadTransaction(Protocol):
    """Small read interface exposed to tool modules."""

    async def fetch_one(
        self, query: LiteralString, parameters: QueryParameters = ()
    ) -> dict[str, Any] | None: ...

    async def fetch_all(
        self, query: LiteralString, parameters: QueryParameters = ()
    ) -> list[dict[str, Any]]: ...


class Database(Protocol):
    """Shared database lifecycle and read-only transaction interface."""

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def readiness(self) -> ReadinessRecord: ...

    async def expire_tenant_locks(self) -> int: ...

    def read_transaction(self) -> AbstractAsyncContextManager[ReadTransaction]: ...


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
           'security.authorize_tenant_operation(uuid,uuid,varchar,bigint,varchar)'
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


async def _activate_runtime_role(connection: AsyncConnection[Any]) -> None:
    """Activate the only NOINHERIT group role allowed for the production login."""
    await connection.execute("SET ROLE gds_app_write")


class _PostgresReadTransaction:
    def __init__(self, connection: AsyncConnection[Any]) -> None:
        self._connection = connection

    async def fetch_one(
        self, query: LiteralString, parameters: QueryParameters = ()
    ) -> dict[str, Any] | None:
        result = await self._connection.execute(query, parameters)
        row: dict[str, Any] | None = await result.fetchone()
        return row

    async def fetch_all(
        self, query: LiteralString, parameters: QueryParameters = ()
    ) -> list[dict[str, Any]]:
        result = await self._connection.execute(query, parameters)
        rows: list[dict[str, Any]] = await result.fetchall()
        return rows


class PostgresDatabase:
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

    @asynccontextmanager
    async def read_transaction(self) -> AsyncIterator[ReadTransaction]:
        try:
            async with self._pool.connection() as connection, connection.transaction():
                await connection.execute("SET TRANSACTION READ ONLY")
                yield _PostgresReadTransaction(connection)
        except PsycopgError as exc:
            raise DependencyUnavailableError() from exc

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

    async def expire_tenant_locks(self) -> int:
        try:
            async with self._pool.connection() as connection, connection.transaction():
                result = await connection.execute(
                    "SELECT security.expire_tenant_locks(%s) AS expired_count",
                    (100,),
                )
                row = await result.fetchone()
            return 0 if row is None else int(row["expired_count"])
        except PsycopgError as exc:
            raise DependencyUnavailableError() from exc
