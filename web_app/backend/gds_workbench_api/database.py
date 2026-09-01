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
       AND to_regclass('application.workflow_stage') IS NOT NULL
       AND to_regclass('application.workflow_stage_variable') IS NOT NULL
       AND to_regclass('application.prompt_template') IS NOT NULL
       AND to_regclass('application.workflow_run_object_selection') IS NOT NULL
       AND to_regclass('application.generated_sql_artifact') IS NOT NULL
       AND to_regclass('model.model_event_log') IS NOT NULL AS schema_ready,
       current_user = 'gds_web_write'
       AND EXISTS (
           SELECT 1
             FROM pg_catalog.pg_roles AS runtime_login
            WHERE runtime_login.rolname = session_user
              AND runtime_login.rolcanlogin
              AND NOT runtime_login.rolsuper
              AND NOT runtime_login.rolinherit
              AND NOT runtime_login.rolcreatedb
              AND NOT runtime_login.rolcreaterole
              AND NOT runtime_login.rolreplication
              AND NOT runtime_login.rolbypassrls
              AND (
                  SELECT count(*)
                    FROM pg_catalog.pg_auth_members AS membership
                   WHERE membership.member = runtime_login.oid
              ) = 1
              AND EXISTS (
                  SELECT 1
                    FROM pg_catalog.pg_auth_members AS membership
                    JOIN pg_catalog.pg_roles AS runtime_group
                      ON runtime_group.oid = membership.roleid
                   WHERE membership.member = runtime_login.oid
                     AND runtime_group.rolname = 'gds_web_write'
                     AND NOT membership.admin_option
                     AND NOT membership.inherit_option
                     AND membership.set_option
              )
       ) AS role_ready,
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
       AND has_function_privilege(
           'gds_web_write',
           'workflow.list_model_object_eligibility(bigint)',
           'EXECUTE'
       )
       AND has_function_privilege(
           'gds_web_write',
           'workflow.list_model_attribute_eligibility(bigint)',
           'EXECUTE'
       )
       AND coalesce(
           has_function_privilege(
               'gds_web_write',
               to_regprocedure(
                   'application.get_profiling_execution_context('
                   'uuid,uuid,character varying,bigint,bigint)'
               ),
               'EXECUTE'
           ),
           FALSE
       )
       AND has_function_privilege(
           'gds_web_write',
           'workflow.list_code_generation_target_context('
           'bigint,character varying,character varying)',
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
       AND NOT EXISTS (
           SELECT 1
             FROM unnest(ARRAY[
                      'mcp.stage_metadata_change_set('
                      || 'uuid,uuid,character varying,bigint,uuid,bigint,jsonb,uuid)',
                      'mcp.get_metadata_change_set(uuid,uuid,character varying,bigint,uuid)',
                      'mcp.record_metadata_change_set_validation('
                      || 'uuid,uuid,character varying,bigint,uuid,bigint,'
                      || 'boolean,character,jsonb,uuid,uuid)',
                      'mcp.apply_metadata_change_set('
                      || 'uuid,uuid,character varying,bigint,uuid,bigint,'
                      || 'character,uuid)',
                      'mcp.archive_metadata_change_set('
                      || 'uuid,uuid,character varying,bigint,uuid,bigint,uuid)'
                  ]) AS required_web_mcp_function(signature)
            WHERE NOT has_function_privilege(
                      'gds_web_write',
                      required_web_mcp_function.signature,
                      'EXECUTE'
                  )
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
       AND NOT has_function_privilege(
           'gds_web_write',
           'mcp.get_databricks_sql_connection_values(bigint,text)',
           'EXECUTE'
       )
       AND NOT EXISTS (
           SELECT 1
             FROM pg_catalog.pg_proc AS mcp_function
             JOIN pg_catalog.pg_namespace AS namespace_record
               ON namespace_record.oid = mcp_function.pronamespace
            WHERE namespace_record.nspname = 'mcp'
              AND has_function_privilege(
                      'gds_web_write',
                      mcp_function.oid,
                      'EXECUTE'
                  )
              AND NOT EXISTS (
                      SELECT 1
                        FROM unnest(ARRAY[
                                 'mcp.create_metadata_change_set('
                                 || 'uuid,uuid,character varying,bigint,uuid,uuid)',
                                 'mcp.stage_metadata_change_set('
                                 || 'uuid,uuid,character varying,bigint,uuid,'
                                 || 'bigint,jsonb,uuid)',
                                 'mcp.get_metadata_change_set('
                                 || 'uuid,uuid,character varying,bigint,uuid)',
                                 'mcp.record_metadata_change_set_validation('
                                 || 'uuid,uuid,character varying,bigint,uuid,bigint,'
                                 || 'boolean,character,jsonb,uuid,uuid)',
                                 'mcp.apply_metadata_change_set('
                                 || 'uuid,uuid,character varying,bigint,uuid,bigint,'
                                 || 'character,uuid)',
                                 'mcp.archive_metadata_change_set('
                                 || 'uuid,uuid,character varying,bigint,uuid,bigint,uuid)'
                             ]) AS allowed_web_mcp_function(signature)
                       WHERE to_regprocedure(
                                 allowed_web_mcp_function.signature
                             ) = mcp_function.oid
                  )
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
       ) AS privileges_ready,
       EXISTS (
           SELECT 1
             FROM information_schema.columns AS column_record
            WHERE column_record.table_schema = 'application'
              AND column_record.table_name = 'workflow_run'
              AND column_record.column_name = 'tenant_id'
              AND column_record.data_type = 'bigint'
              AND column_record.is_nullable = 'NO'
       )
       AND EXISTS (
           SELECT 1
             FROM pg_catalog.pg_constraint AS constraint_record
            WHERE constraint_record.conrelid =
                  'application.workflow_run'::REGCLASS
              AND constraint_record.conname = 'fk_workflow_run_model'
              AND constraint_record.contype = 'f'
              AND constraint_record.convalidated
              AND pg_catalog.pg_get_constraintdef(constraint_record.oid) =
                  'FOREIGN KEY (model_id, tenant_id) '
                  'REFERENCES model.model(model_id, tenant_id)'
       )
       AND EXISTS (
           SELECT 1
             FROM pg_catalog.pg_index AS index_record
             JOIN pg_catalog.pg_class AS index_relation
               ON index_relation.oid = index_record.indexrelid
            WHERE index_record.indrelid = 'application.workflow_run'::REGCLASS
              AND index_relation.relname = 'uq_workflow_run_running_tenant'
              AND index_record.indisunique
              AND index_record.indisvalid
              AND index_record.indisready
              AND index_record.indnkeyatts = 1
              AND pg_catalog.pg_get_indexdef(
                      index_relation.oid,
                      1,
                      TRUE
                  ) = 'tenant_id'
              AND pg_catalog.pg_get_expr(
                      index_record.indpred,
                      index_record.indrelid
                  ) = '((workflow_run_state)::text = ''running''::text)'
       )
       AND EXISTS (
           SELECT 1
             FROM pg_catalog.pg_proc AS function_record
            WHERE function_record.oid = pg_catalog.to_regprocedure(
                      'application.start_workflow_run('
                      'uuid,uuid,character varying,bigint,bigint)'
                  )
              AND function_record.prosecdef
              AND function_record.provolatile = 'v'
              AND function_record.proconfig =
                  ARRAY['search_path=pg_catalog']::TEXT[]
              AND function_record.prosrc LIKE
                  '%active_run.tenant_id = v_run.tenant_id%'
              AND function_record.prosrc LIKE
                  '%uq_workflow_run_running_tenant%'
              AND function_record.prosrc LIKE '%tenant_workflow_conflict%'
       ) AS workflow_guard_ready,
       (SELECT count(*) = 49
          FROM application.workflow_stage)
       AND (SELECT count(*) = 49
              FROM application.workflow_stage
             WHERE is_active)
       AND (SELECT count(*) = 80
              FROM application.workflow_stage_variable)
       AND (SELECT count(*) = 80
              FROM application.workflow_stage_variable
             WHERE is_active) AS application_reference_ready
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
            if not row["workflow_guard_ready"] or not row["application_reference_ready"]:
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
