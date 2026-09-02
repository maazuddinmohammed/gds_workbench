"""Governed multi-statement Databricks SQL MCP tool."""

# Pyright cannot see that @server.tool registers this nested handler.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from re import fullmatch
from typing import Annotated, Any, Literal, LiteralString

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import (
    DatabricksConnectionConfigurationError,
    DatabricksConnectionNotFoundError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import (
    DatabricksConnectionDatabase,
    DatabricksConnectionValuesRecord,
    ReadIsolation,
)

from .executor import DatabricksSqlConnection, DatabricksSqlExecutor
from .validation import validate_databricks_sql

_TOOL_NAME = "execute_databricks_sql"
_MAX_SQL_CHARACTERS = 100_000
POLICY = ToolPolicy.TENANT_READ

_CONNECTION_SQL: LiteralString = """
SELECT connection.tenant_id
  FROM core.connection AS connection
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = connection.tenant_id
   AND tenant.is_active
 WHERE connection.connection_id = %s
   AND connection.is_active
   AND NOT connection.is_global_data_store
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExecuteDatabricksSqlResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    connection_id: int = Field(gt=0)
    environment_code: str = Field(min_length=1, max_length=100)
    statement_count: int = Field(gt=0, le=25)
    row_limit: int = Field(gt=0, le=50)
    columns: tuple[str, ...] = Field(max_length=500)
    rows: tuple[tuple[JsonValue, ...], ...] = Field(max_length=50)
    row_count: int = Field(ge=0, le=50)
    rows_truncated: bool
    cells_truncated: bool


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_execute_databricks_sql_tool(
    server: MCPServer[None],
    *,
    database: DatabricksConnectionDatabase,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
    executor: DatabricksSqlExecutor,
    max_rows: int,
    timeout_seconds: int,
) -> None:
    @server.tool(
        description=(
            "Execute up to 25 governed Databricks SQL statements using an active source "
            "Connection, its Tenant's Global Data Store Connection, and one requested "
            "Environment; environment_code defaults to dev. Physical relations must use "
            "catalog.schema.table. Allows reads "
            "and unqualified temporary views/tables only. "
            "Returns the configured row limit, never more than 50, from the final "
            "statement. The audit log retains only a digest and bounded metadata, "
            "never submitted SQL or credentials."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        ),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def execute_databricks_sql(
        ctx: Context[None],
        connection_id: Annotated[
            int,
            Field(
                gt=0,
                description=(
                    "Active non-GDS source Connection. The server resolves that Tenant's "
                    "Global Data Store Connection and the requested Environment."
                ),
            ),
        ],
        sql: Annotated[
            str,
            Field(
                min_length=1,
                max_length=_MAX_SQL_CHARACTERS,
                description=(
                    "One to 25 Databricks SQL statements containing reads and unqualified "
                    "temporary views or tables only; persistent relations must be fully qualified."
                ),
            ),
        ],
        environment_code: Annotated[
            str,
            Field(
                min_length=1,
                max_length=100,
                description="Registered Environment code; defaults to lowercase dev.",
            ),
        ] = "dev",
        schema_version: Literal["1.0"] = "1.0",
    ) -> ExecuteDatabricksSqlResult:
        try:
            batch = validate_databricks_sql(sql)
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                connection_row = await transaction.fetch_one(
                    _CONNECTION_SQL,
                    (connection_id,),
                )
                if connection_row is None:
                    raise DatabricksConnectionNotFoundError()
                tenant_id = int(connection_row["tenant_id"])
                await authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=POLICY,
                )

            values = await database.read_databricks_connection_values(
                connection_id,
                environment_code,
            )
            connection = _validated_connection(
                values,
                tenant_id=tenant_id,
                environment_code=environment_code,
            )
            execution = await executor.execute(
                connection=connection,
                batch=batch,
                max_rows=max_rows,
                timeout_seconds=timeout_seconds,
            )
            return ExecuteDatabricksSqlResult(
                connection_id=connection_id,
                environment_code=values.environment_code or environment_code,
                statement_count=len(batch.statements),
                row_limit=max_rows,
                columns=execution.columns,
                rows=execution.rows,
                row_count=len(execution.rows),
                rows_truncated=execution.rows_truncated,
                cells_truncated=execution.cells_truncated,
            )
        except AuthenticationError as error:
            raise SafeToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise SafeToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise SafeToolError("internal_error: The operation could not be completed.") from None

    audit.register_tool(
        _TOOL_NAME,
        policy=POLICY,
        summarize_input=_audit_input_metadata,
        retain_arguments={"connection_id", "environment_code", "schema_version"},
    )


def _validated_connection(
    values: DatabricksConnectionValuesRecord,
    *,
    tenant_id: int,
    environment_code: str,
) -> DatabricksSqlConnection:
    if values.failure_code == "connection_not_found":
        raise DatabricksConnectionNotFoundError()
    if values.failure_code == "connection_values_missing":
        raise DatabricksConnectionConfigurationError("missing")
    if values.failure_code == "environment_not_found":
        raise DatabricksConnectionConfigurationError("environment")
    if values.failure_code == "gds_connection_not_found":
        raise DatabricksConnectionConfigurationError("global_connection")
    if (
        values.failure_code is not None
        or values.tenant_id != tenant_id
        or values.gds_connection_id is None
        or values.gds_connection_id < 1
        or values.environment_code is None
        or values.environment_code.strip().casefold() != environment_code.strip().casefold()
    ):
        raise DatabricksConnectionConfigurationError("invalid")

    host = values.server_hostname
    path = values.http_path
    token = values.access_token
    if (
        host is None
        or path is None
        or token is None
        or len(host) > 255
        or fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host) is None
        or fullmatch(r"/sql/1\.0/warehouses/[A-Za-z0-9-]{1,128}", path) is None
        or not 1 <= len(token) <= 8192
        or token != token.strip()
    ):
        raise DatabricksConnectionConfigurationError("invalid")

    return DatabricksSqlConnection(
        server_hostname=host,
        http_path=path,
        access_token=token,
    )


def _audit_input_metadata(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    connection_id = arguments.get("connection_id")
    environment_code = arguments.get("environment_code", "dev")
    sql = arguments.get("sql")
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "connection_id": (
            connection_id if type(connection_id) is int and connection_id > 0 else "invalid"
        ),
        "environment_code": (
            environment_code
            if isinstance(environment_code, str) and environment_code.strip()
            else "invalid"
        ),
        "sql_character_count": len(sql) if isinstance(sql, str) else "invalid",
        "sql_sha256": (
            hashlib.sha256(sql.encode("utf-8")).hexdigest() if isinstance(sql, str) else "invalid"
        ),
    }
