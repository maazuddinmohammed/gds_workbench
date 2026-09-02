"""Tenant header and bounded Connection-grain catalog summary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import TenantRole, ToolPolicy
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation
from gds_etl_workbench.tools.catalog.visibility import VISIBLE_OBJECTS_CTE

_TOOL_NAME = "get_tenant_details"
_MAX_CONNECTIONS = 200
POLICY = ToolPolicy.TENANT_READ

_TENANT_SQL: LiteralString = """
SELECT tenant.tenant_id,
       tenant.tenant_code,
       tenant.tenant_name,
       left(tenant.tenant_description, 2000) AS tenant_description,
       tenant.tenant_visibility
  FROM core.tenant AS tenant
 WHERE tenant.tenant_id = %s
   AND tenant.is_active
"""

_CONNECTIONS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE},
relevant_connection_ids AS (
    SELECT connection.connection_id
      FROM requested_tenant
      JOIN core.connection AS connection
        ON connection.tenant_id = requested_tenant.tenant_id
    UNION
    SELECT requested_tenant.gds_connection_id
      FROM requested_tenant
     WHERE requested_tenant.gds_connection_id IS NOT NULL
    UNION
    SELECT object.connection_id
      FROM visible_objects
      JOIN core.object AS object ON object.object_id = visible_objects.object_id
),
connection_rows AS (
    SELECT connection.connection_id,
           connection.connection_code,
           connection.connection_name,
           connection.is_global_data_store,
           connection.is_active,
           system.system_id,
           system.system_code,
           system.system_name,
           system_type.system_type_code,
           system_type.system_type_name,
           connection_type.connection_type_code,
           connection_type.connection_type_name,
           connection.connection_id = requested_tenant.gds_connection_id
               AS is_tenant_gds_connection,
           EXISTS (
               SELECT 1
                 FROM core.object AS tenant_object
                WHERE tenant_object.source_tenant_id = requested_tenant.tenant_id
                  AND tenant_object.connection_id = connection.connection_id
           ) AS contains_tenant_objects,
           count(object.object_id) FILTER (
               WHERE object.is_active AND zone.zone_code = 'source'
           ) AS source_object_count,
           count(object.object_id) FILTER (
               WHERE object.is_active AND zone.zone_code = 'bronze'
           ) AS bronze_object_count,
           count(object.object_id) FILTER (
               WHERE object.is_active AND zone.zone_code = 'silver'
           ) AS silver_object_count,
           count(object.object_id) FILTER (
               WHERE object.is_active AND zone.zone_code = 'gold'
           ) AS gold_object_count
      FROM requested_tenant
      JOIN relevant_connection_ids AS relevant
        ON relevant.connection_id IS NOT NULL
      JOIN core.connection AS connection
        ON connection.connection_id = relevant.connection_id
      JOIN core.system AS system ON system.system_id = connection.system_id
      JOIN reference.system_type AS system_type
        ON system_type.system_type_id = system.system_type_id
      JOIN reference.connection_type AS connection_type
        ON connection_type.connection_type_id = connection.connection_type_id
      LEFT JOIN core.object AS object
        ON object.connection_id = connection.connection_id
       AND EXISTS (
           SELECT 1 FROM visible_objects
            WHERE visible_objects.object_id = object.object_id
       )
      LEFT JOIN reference.zone AS zone ON zone.zone_id = object.zone_id
     GROUP BY connection.connection_id,
              system.system_id,
              system_type.system_type_id,
              connection_type.connection_type_id,
              requested_tenant.gds_connection_id,
              requested_tenant.tenant_id
)
SELECT connection_rows.*,
       count(*) OVER () AS total_connection_count
  FROM connection_rows
 ORDER BY lower(connection_name), connection_id
 LIMIT 201
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TenantDetails(ContractModel):
    tenant_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    tenant_name: str = Field(min_length=1, max_length=200)
    tenant_description: str | None = Field(default=None, max_length=2000)
    tenant_visibility: Literal["global", "private"]
    effective_role: TenantRole


class ObjectZoneCounts(ContractModel):
    source: int = Field(ge=0)
    bronze: int = Field(ge=0)
    silver: int = Field(ge=0)
    gold: int = Field(ge=0)


class TenantConnectionSummary(ContractModel):
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    connection_name: str = Field(min_length=1, max_length=200)
    connection_type_code: str = Field(min_length=1, max_length=100)
    connection_type_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    system_type_code: str = Field(min_length=1, max_length=100)
    system_type_name: str = Field(min_length=1, max_length=200)
    is_global_data_store: bool = Field(
        description="True when this Connection is designated as a Global Data Store."
    )
    is_tenant_gds_connection: bool = Field(
        description="True only for this Tenant's exact Bronze/Silver/Gold placement Connection."
    )
    contains_tenant_objects: bool = Field(
        description="True when the Connection contains Objects owned by the requested Tenant."
    )
    is_active: bool
    active_object_counts: ObjectZoneCounts


class GetTenantDetailsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant: TenantDetails
    connection_count: int = Field(ge=0)
    connections: tuple[TenantConnectionSummary, ...] = Field(max_length=_MAX_CONNECTIONS)
    connections_truncated: bool


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_get_tenant_details_tool(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        name=_TOOL_NAME,
        description=(
            "Get one authorized Tenant and every relevant Connection with System and type "
            "details plus active Object counts by zone. For Bronze, Silver, or Gold placement, "
            "use the active row where is_tenant_gds_connection=true and verify "
            "is_global_data_store=true."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def _get_tenant_details(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetTenantDetailsResult:
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                authorization = await authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=POLICY,
                )
                tenant = await transaction.fetch_one(_TENANT_SQL, (tenant_id,))
                rows = await transaction.fetch_all(_CONNECTIONS_SQL, (tenant_id,))
            if tenant is None:
                raise RuntimeError("authorized Tenant disappeared from its read snapshot")
            connection_count = 0 if not rows else int(rows[0]["total_connection_count"])
            connections = tuple(_connection(row) for row in rows[:_MAX_CONNECTIONS])
            return GetTenantDetailsResult(
                tenant=TenantDetails(
                    **tenant,
                    effective_role=authorization.effective_role,
                ),
                connection_count=connection_count,
                connections=connections,
                connections_truncated=connection_count > _MAX_CONNECTIONS,
            )
        except AuthenticationError as error:
            raise SafeToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise SafeToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise SafeToolError("internal_error: The operation could not be completed.") from None

    del _get_tenant_details
    audit.register_tool(
        _TOOL_NAME,
        policy=POLICY,
        summarize_input=_audit_input_metadata,
        retain_arguments={"tenant_id", "schema_version"},
        tenant_argument="tenant_id",
    )


def _connection(row: Mapping[str, Any]) -> TenantConnectionSummary:
    return TenantConnectionSummary(
        connection_id=row["connection_id"],
        connection_code=row["connection_code"],
        connection_name=row["connection_name"],
        connection_type_code=row["connection_type_code"],
        connection_type_name=row["connection_type_name"],
        system_id=row["system_id"],
        system_code=row["system_code"],
        system_name=row["system_name"],
        system_type_code=row["system_type_code"],
        system_type_name=row["system_type_name"],
        is_global_data_store=row["is_global_data_store"],
        is_tenant_gds_connection=row["is_tenant_gds_connection"],
        contains_tenant_objects=row["contains_tenant_objects"],
        is_active=row["is_active"],
        active_object_counts=ObjectZoneCounts(
            source=row["source_object_count"],
            bronze=row["bronze_object_count"],
            silver=row["silver_object_count"],
            gold=row["gold_object_count"],
        ),
    )


def _audit_input_metadata(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    tenant_id = arguments.get("tenant_id")
    return {
        "schema_version": "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid",
        "tenant_id": tenant_id if type(tenant_id) is int and tenant_id > 0 else "invalid",
    }
