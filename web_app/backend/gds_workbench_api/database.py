"""Least-privilege PostgreSQL adapter for the web runtime role."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, LiteralString

from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from psycopg import AsyncConnection
from psycopg import Error as PsycopgError
from psycopg.errors import InsufficientPrivilege
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

type QueryParameters = tuple[Any, ...]

_READINESS_SQL = """
SELECT current_setting('server_version_num')::INTEGER / 10000 AS postgres_major,
       to_regclass('application.workflow_run') IS NOT NULL
       AND to_regclass('application.prompt_template') IS NOT NULL
       AND to_regclass('application.workflow_run_object_selection') IS NOT NULL
       AND to_regclass('application.generated_sql_artifact') IS NOT NULL
       AND to_regclass('model.model_event_log') IS NOT NULL AS schema_ready,
       pg_has_role(session_user, 'gds_web_write', 'SET') AS role_ready,
       has_table_privilege(
           'gds_web_write',
           'application.workflow_run',
           'SELECT'
       )
       AND has_function_privilege(
           'gds_web_write',
           'application.create_model(uuid,uuid,character varying,bigint,'
           'character varying,character varying,text,jsonb,text,jsonb,jsonb,'
           'character varying,character varying,character varying,'
           'character varying,integer,integer)',
           'EXECUTE'
       )
       AND has_function_privilege(
           'gds_web_write',
           'workflow.list_tenant_visible_objects(bigint)',
           'EXECUTE'
       )
       AND has_table_privilege(
           'gds_web_write',
           'mcp.model_change_set',
           'SELECT,INSERT,UPDATE'
       )
       AND has_function_privilege(
           'gds_web_write',
           'mcp.create_metadata_change_set('
           'uuid,uuid,character varying,bigint,uuid,uuid)',
           'EXECUTE'
       )
       AND NOT has_table_privilege(
           'gds_web_write',
           'mcp.metadata_change_set',
           'SELECT,INSERT,UPDATE,DELETE'
       )
       AND NOT has_function_privilege(
           'gds_web_write',
           'mcp.begin_metadata_stage_batch('
           'uuid,uuid,character varying,bigint,uuid,bigint,uuid,'
           'character varying,integer,integer,character,uuid)',
           'EXECUTE'
       )
       AND has_table_privilege(
           'gds_web_write',
           'workflow.conceptual_object',
           'SELECT,INSERT,UPDATE'
       )
       AND NOT has_table_privilege(
           'gds_web_write',
           'workflow.attribute_profile',
           'INSERT,UPDATE'
       )
       AND NOT has_table_privilege(
           'gds_web_write',
           'core.connection_value',
           'SELECT'
       ) AS privileges_ready
"""


class _WebTransaction:
    def __init__(self, connection: AsyncConnection[Any]) -> None:
        self._connection = connection

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: QueryParameters = (),
    ) -> dict[str, Any] | None:
        result = await self._connection.execute(query, parameters)
        row: dict[str, Any] | None = await result.fetchone()
        return row

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: QueryParameters = (),
    ) -> list[dict[str, Any]]:
        result = await self._connection.execute(query, parameters)
        rows: list[dict[str, Any]] = await result.fetchall()
        return rows


class WebPostgresDatabase:
    def __init__(
        self,
        *,
        dsn: str,
        pool_min: int,
        pool_max: int,
        pool_timeout_seconds: int,
    ) -> None:
        self._pool = AsyncConnectionPool(
            conninfo=dsn,
            min_size=pool_min,
            max_size=pool_max,
            timeout=pool_timeout_seconds,
            kwargs={"autocommit": True, "row_factory": dict_row},
            open=False,
            name="gds-web",
        )

    async def open(self) -> None:
        await self._pool.open(wait=False)

    async def close(self) -> None:
        await self._pool.close()

    async def readiness(self) -> ReadinessRecord:
        try:
            async with self._transaction(read_only=True) as connection:
                result = await connection.execute(_READINESS_SQL)
                row = await result.fetchone()
            if row is None or row["postgres_major"] != 18:
                return ReadinessRecord(ready=False, code="database_version_invalid")
            if not row["schema_ready"]:
                return ReadinessRecord(ready=False, code="database_schema_unavailable")
            if not row["role_ready"] or not row["privileges_ready"]:
                return ReadinessRecord(ready=False, code="database_role_invalid")
            return ReadinessRecord(ready=True, code="ready")
        except InsufficientPrivilege:
            return ReadinessRecord(ready=False, code="database_role_invalid")
        except PsycopgError:
            return ReadinessRecord(ready=False, code="database_unavailable")

    @asynccontextmanager
    async def _transaction(
        self,
        *,
        read_only: bool,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[AsyncConnection[Any]]:
        async with self._pool.connection() as connection, connection.transaction():
            if isolation is ReadIsolation.REPEATABLE_READ:
                statement = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
                if read_only:
                    statement += ", READ ONLY"
                await connection.execute(statement)
            elif read_only:
                await connection.execute("SET TRANSACTION READ ONLY")
            await connection.execute("SET LOCAL ROLE gds_web_write")
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
                yield _WebTransaction(connection)
        except PsycopgError as exc:
            raise DependencyUnavailableError() from exc

    @asynccontextmanager
    async def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[WriteTransaction]:
        try:
            async with self._transaction(
                read_only=False,
                isolation=isolation,
            ) as connection:
                yield _WebTransaction(connection)
        except PsycopgError as exc:
            raise DependencyUnavailableError() from exc
