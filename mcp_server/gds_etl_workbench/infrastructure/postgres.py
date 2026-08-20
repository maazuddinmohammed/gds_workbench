"""Least-privilege PostgreSQL persistence adapter."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, LiteralString, Protocol
from uuid import UUID

from psycopg import AsyncConnection
from psycopg import Error as PsycopgError
from psycopg.errors import InsufficientPrivilege
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from gds_etl_workbench.domain.authorization import ActorKind, ToolPolicy
from gds_etl_workbench.domain.errors import DependencyUnavailableError

type QueryParameters = tuple[Any, ...]


class ReadIsolation(StrEnum):
    READ_COMMITTED = "read_committed"
    REPEATABLE_READ = "repeatable_read"


@dataclass(frozen=True, slots=True)
class ReadinessRecord:
    ready: bool
    code: str


@dataclass(frozen=True, slots=True)
class ToolCallLogRecord:
    """One server-derived MCP tool-call audit record."""

    tool_call_id: UUID
    principal_id: int | None
    principal_display_name: str
    actor_kind: ActorKind
    tool_name: str
    tool_policy: ToolPolicy
    tenant_id: int | None
    input_metadata: Mapping[str, Any]
    status: Literal["succeeded", "failed"]
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class DatabricksConnectionValuesRecord:
    tenant_id: int | None
    failure_code: str | None
    server_hostname: str | None = field(repr=False)
    http_path: str | None = field(repr=False)
    access_token: str | None = field(repr=False)


class ReadTransaction(Protocol):
    """Small read interface exposed to tool modules."""

    async def fetch_one(
        self, query: LiteralString, parameters: QueryParameters = ()
    ) -> dict[str, Any] | None: ...

    async def fetch_all(
        self, query: LiteralString, parameters: QueryParameters = ()
    ) -> list[dict[str, Any]]: ...


class WriteTransaction(ReadTransaction, Protocol):
    """Small write interface limited to fixed tool-owned SQL calls."""


class Database(Protocol):
    """Shared database lifecycle, read, and audit interface."""

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def readiness(self) -> ReadinessRecord: ...

    async def expire_tenant_locks(self) -> int: ...

    async def append_tool_call_log(self, record: ToolCallLogRecord) -> None: ...

    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabricksConnectionDatabase(Database, Protocol):
    """Database boundary for the exact governed Databricks secret lookup."""

    async def read_databricks_connection_values(
        self,
        connection_id: int,
    ) -> DatabricksConnectionValuesRecord: ...


class WriteDatabase(Database, Protocol):
    """Database boundary for fixed, governed write operations."""

    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


_READINESS_BOOTSTRAP_SQL = """
SELECT current_setting('server_version_num')::INTEGER / 10000 AS postgres_major,
       to_regprocedure('mcp.runtime_readiness()') IS NOT NULL AS contract_exists
"""

_READINESS_SQL = """
SELECT schema_version,
       postgres_major,
       schema_shape_ok,
       runtime_role_ok,
       runtime_privileges_ok,
       runtime_query_contract_ok
  FROM mcp.runtime_readiness()
"""

_APPEND_TOOL_CALL_LOG_SQL = """
INSERT INTO mcp.tool_call_log (
    tool_call_id,
    principal_id,
    principal_display_name,
    actor_kind,
    tool_name,
    tool_policy,
    tenant_id,
    input_metadata,
    tool_call_status,
    failure_code
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_READ_DATABRICKS_CONNECTION_VALUES_SQL = """
SELECT connection_tenant_id,
       failure_code,
       databricks_host_name,
       databricks_http_path,
       databricks_token
  FROM mcp.get_databricks_sql_connection_values(%s)
"""


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
        expected_schema_version: str = "1.0.0",
    ) -> None:
        self._require_runtime_role = require_runtime_role
        self._expected_schema_version = expected_schema_version
        self._pool = AsyncConnectionPool(
            conninfo=dsn,
            min_size=pool_min,
            max_size=pool_max,
            timeout=pool_timeout_seconds,
            kwargs={"autocommit": True, "row_factory": dict_row},
            open=False,
            name="gds-mcp",
        )

    async def open(self) -> None:
        await self._pool.open(wait=False)

    async def close(self) -> None:
        await self._pool.close()

    @asynccontextmanager
    async def _transaction(
        self,
        *,
        read_only: bool,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[AsyncConnection[Any]]:
        async with self._pool.connection() as connection, connection.transaction():
            if read_only:
                if isolation is ReadIsolation.REPEATABLE_READ:
                    await connection.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                    )
                else:
                    await connection.execute("SET TRANSACTION READ ONLY")
            if self._require_runtime_role:
                await connection.execute("SET LOCAL ROLE gds_app_write")
            yield connection

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        try:
            async with self._transaction(
                read_only=True,
                isolation=isolation,
            ) as connection:
                yield _PostgresReadTransaction(connection)
        except PsycopgError as exc:
            raise DependencyUnavailableError() from exc

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[WriteTransaction]:
        try:
            async with self._transaction(read_only=False) as connection:
                yield _PostgresReadTransaction(connection)
        except PsycopgError as exc:
            raise DependencyUnavailableError() from exc

    async def readiness(self) -> ReadinessRecord:
        try:
            # The readiness contract exercises check_tenant_lock(), whose
            # SELECT ... FOR SHARE query is invalid in a read-only transaction.
            async with self._transaction(read_only=False) as connection:
                bootstrap_result = await connection.execute(_READINESS_BOOTSTRAP_SQL)
                bootstrap = await bootstrap_result.fetchone()
                if bootstrap is None:
                    return ReadinessRecord(ready=False, code="database_posture_invalid")
                if bootstrap["postgres_major"] != 18:
                    return ReadinessRecord(ready=False, code="database_version_invalid")
                if not bootstrap["contract_exists"]:
                    return ReadinessRecord(
                        ready=False,
                        code="database_schema_unavailable",
                    )
                result = await connection.execute(_READINESS_SQL)
                row = await result.fetchone()
            if row is None:
                return ReadinessRecord(ready=False, code="database_posture_invalid")
            if row["schema_version"] != self._expected_schema_version:
                return ReadinessRecord(ready=False, code="database_schema_unavailable")
            if row["postgres_major"] != 18:
                return ReadinessRecord(ready=False, code="database_version_invalid")
            if not row["schema_shape_ok"]:
                return ReadinessRecord(ready=False, code="database_schema_unavailable")
            if self._require_runtime_role and (
                not row["runtime_role_ok"] or not row["runtime_privileges_ok"]
            ):
                return ReadinessRecord(ready=False, code="database_role_invalid")
            if not row["runtime_query_contract_ok"]:
                return ReadinessRecord(ready=False, code="database_schema_unavailable")
            return ReadinessRecord(ready=True, code="ready")
        except InsufficientPrivilege:
            return ReadinessRecord(ready=False, code="database_role_invalid")
        except PsycopgError:
            return ReadinessRecord(ready=False, code="database_unavailable")

    async def expire_tenant_locks(self) -> int:
        try:
            async with self._transaction(read_only=False) as connection:
                result = await connection.execute(
                    "SELECT security.expire_tenant_locks(%s) AS expired_count",
                    (100,),
                )
                row = await result.fetchone()
            return 0 if row is None else int(row["expired_count"])
        except PsycopgError as exc:
            raise DependencyUnavailableError() from exc

    async def append_tool_call_log(self, record: ToolCallLogRecord) -> None:
        try:
            async with self._transaction(read_only=False) as connection:
                await connection.execute(
                    _APPEND_TOOL_CALL_LOG_SQL,
                    (
                        record.tool_call_id,
                        record.principal_id,
                        record.principal_display_name,
                        record.actor_kind.value,
                        record.tool_name,
                        record.tool_policy.value,
                        record.tenant_id,
                        Jsonb(dict(record.input_metadata)),
                        record.status,
                        record.failure_code,
                    ),
                )
        except PsycopgError as exc:
            raise DependencyUnavailableError() from exc

    async def read_databricks_connection_values(
        self,
        connection_id: int,
    ) -> DatabricksConnectionValuesRecord:
        try:
            async with self._transaction(read_only=True) as connection:
                result = await connection.execute(
                    _READ_DATABRICKS_CONNECTION_VALUES_SQL,
                    (connection_id,),
                )
                row = await result.fetchone()
            if row is None:
                raise DependencyUnavailableError()
            return DatabricksConnectionValuesRecord(
                tenant_id=row["connection_tenant_id"],
                failure_code=row["failure_code"],
                server_hostname=row["databricks_host_name"],
                http_path=row["databricks_http_path"],
                access_token=row["databricks_token"],
            )
        except PsycopgError as exc:
            raise DependencyUnavailableError() from exc
