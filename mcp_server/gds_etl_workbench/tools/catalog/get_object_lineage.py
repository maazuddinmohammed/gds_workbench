"""Direct configured ingestion lineage for one authorized physical Object."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

from .visibility import VISIBLE_OBJECTS_CTE

type Direction = Literal["upstream", "downstream", "both"]
type EdgeDirection = Literal["upstream", "downstream"]
type ZoneCode = Literal["source", "bronze", "silver", "gold"]

_TOOL_NAME = "get_object_lineage"
_MAX_MAPPINGS = 500
POLICY = ToolPolicy.TENANT_READ

_LINEAGE_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT mapping.ingestion_object_mapping_id,
       mapping.is_active,
       CASE
           WHEN mapping.target_object_id = %s THEN 'upstream'
           ELSE 'downstream'
       END AS direction,
       source_object.object_id AS source_object_id,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       source_zone.zone_code AS source_zone,
       source_connection.connection_id AS source_connection_id,
       source_connection.connection_name AS source_connection_name,
       source_tenant.tenant_id AS source_tenant_id,
       source_tenant.tenant_name AS source_tenant_name,
       target_object.object_id AS target_object_id,
       target_object.object_schema AS target_object_schema,
       target_object.object_name AS target_object_name,
       target_zone.zone_code AS target_zone,
       target_connection.connection_id AS target_connection_id,
       target_connection.connection_name AS target_connection_name,
       target_tenant.tenant_id AS target_tenant_id,
       target_tenant.tenant_name AS target_tenant_name,
       (
           SELECT count(*)
             FROM core.ingestion_attribute_mapping AS attribute_mapping
            WHERE attribute_mapping.ingestion_object_mapping_id =
                  mapping.ingestion_object_mapping_id
       ) AS attribute_mapping_count,
       (
           SELECT count(*)
             FROM core.copy
             JOIN core.copy_group
               ON copy_group.copy_group_id = copy.copy_group_id
            WHERE copy.ingestion_object_mapping_id = mapping.ingestion_object_mapping_id
              AND copy_group.tenant_id = (
                  SELECT requested_tenant.tenant_id FROM requested_tenant
              )
       ) AS copy_count
  FROM core.ingestion_object_mapping AS mapping
  JOIN visible_objects AS source_visible
    ON source_visible.object_id = mapping.source_object_id
  JOIN visible_objects AS target_visible
    ON target_visible.object_id = mapping.target_object_id
  JOIN core.object AS source_object
    ON source_object.object_id = mapping.source_object_id
  JOIN reference.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
  JOIN core.connection AS source_connection
    ON source_connection.connection_id = source_object.connection_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = source_connection.tenant_id
  JOIN core.object AS target_object
    ON target_object.object_id = mapping.target_object_id
  JOIN reference.zone AS target_zone ON target_zone.zone_id = target_object.zone_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = target_connection.tenant_id
 WHERE (
       (%s IN ('upstream', 'both') AND mapping.target_object_id = %s)
       OR (%s IN ('downstream', 'both') AND mapping.source_object_id = %s)
   )
 ORDER BY mapping.ingestion_object_mapping_id
 LIMIT 501
"""

_OBJECT_VISIBLE_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT EXISTS (
    SELECT 1 FROM visible_objects WHERE visible_objects.object_id = %s
) AS is_visible
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LineageObjectReference(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    zone: ZoneCode
    connection_id: int = Field(gt=0)
    connection_name: str = Field(min_length=1, max_length=200)
    owning_tenant_id: int = Field(gt=0)
    owning_tenant_name: str = Field(min_length=1, max_length=200)


class IngestionMappingSummary(ContractModel):
    ingestion_object_mapping_id: int = Field(gt=0)
    direction: EdgeDirection
    source_object: LineageObjectReference
    target_object: LineageObjectReference
    attribute_mapping_count: int = Field(ge=0)
    copy_count: int = Field(ge=0)
    is_active: bool


class GetObjectLineageResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    object_id: int = Field(gt=0)
    mappings: tuple[IngestionMappingSummary, ...] = Field(max_length=_MAX_MAPPINGS)
    mappings_truncated: bool


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_get_object_lineage_tool(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Get direct configured ingestion mappings upstream and/or downstream of one "
            "authorized Object. This reports configured lineage, not observed runtime flow."
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
    async def get_object_lineage(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        object_id: Annotated[int, Field(gt=0)],
        direction: Direction = "both",
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetObjectLineageResult:
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=POLICY,
                )
                visibility = await transaction.fetch_one(
                    _OBJECT_VISIBLE_SQL,
                    (tenant_id, object_id),
                )
                if visibility is None or not visibility["is_visible"]:
                    raise InvalidRequestError("Object was not found.")
                rows = await transaction.fetch_all(
                    _LINEAGE_SQL,
                    (tenant_id, object_id, direction, object_id, direction, object_id),
                )
            return GetObjectLineageResult(
                tenant_id=tenant_id,
                object_id=object_id,
                mappings=tuple(_mapping(row) for row in rows[:_MAX_MAPPINGS]),
                mappings_truncated=len(rows) > _MAX_MAPPINGS,
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
        retain_arguments={"tenant_id", "object_id", "direction", "schema_version"},
        tenant_argument="tenant_id",
    )


def _mapping(row: Mapping[str, Any]) -> IngestionMappingSummary:
    return IngestionMappingSummary(
        ingestion_object_mapping_id=row["ingestion_object_mapping_id"],
        direction=row["direction"],
        source_object=_object_reference(row, prefix="source"),
        target_object=_object_reference(row, prefix="target"),
        attribute_mapping_count=row["attribute_mapping_count"],
        copy_count=row["copy_count"],
        is_active=row["is_active"],
    )


def _object_reference(
    row: Mapping[str, Any], *, prefix: Literal["source", "target"]
) -> LineageObjectReference:
    return LineageObjectReference(
        object_id=row[f"{prefix}_object_id"],
        object_schema=row[f"{prefix}_object_schema"],
        object_name=row[f"{prefix}_object_name"],
        zone=row[f"{prefix}_zone"],
        connection_id=row[f"{prefix}_connection_id"],
        connection_name=row[f"{prefix}_connection_name"],
        owning_tenant_id=row[f"{prefix}_tenant_id"],
        owning_tenant_name=row[f"{prefix}_tenant_name"],
    )


def _audit_input_metadata(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    tenant_id = arguments.get("tenant_id")
    object_id = arguments.get("object_id")
    direction = arguments.get("direction", "both")
    return {
        "schema_version": "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid",
        "tenant_id": tenant_id if type(tenant_id) is int and tenant_id > 0 else "invalid",
        "object_id": object_id if type(object_id) is int and object_id > 0 else "invalid",
        "direction": (direction if direction in {"upstream", "downstream", "both"} else "invalid"),
    }
